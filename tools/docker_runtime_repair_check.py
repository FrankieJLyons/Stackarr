"""Runtime repair/storage faults restricted to a new two-app Docker lab."""

import argparse
import ctypes
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from stackarr.arr_logins import read as arr_login
from stackarr.deployment import DeploymentError, Deployments
from stackarr.deployment_check import inspect_container, load_receipt
from stackarr.self_update import FINGERPRINT, TERMINAL, SelfUpdates, fingerprint, pending, read, write
from stackarr.store import Store
from stackarr.updates import Updates
from tools import docker_app_maintenance_check as preservation
from tools.docker_folder_ports_check import bootstrap, command, hashes
from tools.docker_host_recovery_check import api, login, wait_job

ROOT = Path("test-results/docker-runtime-repair-20261018-r2").resolve()
STATE = ROOT / "package-state"
PACKAGE = Path("test-results/runtime-repair-package-extracted-r2/Stackarr-Docker-Runtime-Repair-Preview-20261018-r2").resolve()
ORIGIN = "http://localhost:29260"


def output(name, value):
    write(ROOT / name, value)


def updater():
    return SelfUpdates(STATE, PACKAGE)


def host():
    assert pending(STATE) is None
    return Deployments(Store(STATE / "controller/state"))


def wait(identity, expected="succeeded"):
    last = None
    for _ in range(1200):
        value = read(updater().home / "jobs" / identity / "job.json")
        if value["phase"] != last:
            print("Isolated Stackarr repair: " + value["phase"], flush=True)
            last = value["phase"]
        if value["phase"] in TERMINAL | {"needs-recovery"}:
            assert value["phase"] == expected, value.get("failure", value["message"])
            return value
        time.sleep(.5)
    raise AssertionError("Runtime repair worker timed out")


def frozen(mode, request=None, status=0):
    report = ROOT / ("frozen-" + mode + "-" + uuid.uuid4().hex[:8] + ".json")
    args = [str(PACKAGE / "StackarrPreview.exe")]
    if mode == "start":
        args += ["--stackarr-start", str(STATE)]
    else:
        args += ["--stackarr-repair-" + mode, str(request)]
    result = subprocess.run([*args, "--maintenance-report", str(report)], capture_output=True, timeout=600,
        creationflags=subprocess.CREATE_NO_WINDOW, env=os.environ | {"STACKARR_PACKAGE_ROOT": str(PACKAGE), "PYINSTALLER_RESET_ENVIRONMENT": "1"})
    assert result.returncode == status and report.exists(), "Frozen runtime operation did not produce the expected report."
    return read(report)


def stop_controller():
    directory = str((STATE / "controller").resolve())
    assert Path(directory).is_relative_to(ROOT)
    env = os.environ | {"STACKARR_RUNTIME_REPAIR_CONTROLLER": directory}
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Process -Filter \"Name='StackarrPreview.exe'\" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($env:STACKARR_RUNTIME_REPAIR_CONTROLLER) -and $_.CommandLine.Contains('--controller-serve') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
        env=env, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0


def preserved(runtime=True):
    preservation.OUTPUT = ROOT
    preservation.main_preserved()
    assert hashes(ROOT / "media") == read(ROOT / "media-before.json")
    if not (ROOT / "lab-before.json").exists():
        return
    before = read(ROOT / "lab-before.json")
    service = host()
    payload = load_receipt(service, before["deployment"])
    assert fingerprint(service.store.root) == before["controller"]
    for key in payload["apps"]:
        info = inspect_container(service, before["deployment"], payload, key)
        assert info["Id"] == before["apps"][key] and info["State"]["Running"]
        assert Updates(service).protected(payload, key, service.store.secret(key)) == before["protected"][key]
        assert arr_login(service, before["deployment"], payload, key, service.store.secret(key)["api_key"])
    if runtime:
        u = updater()
        value = u.protected(u.active())
        assert value["dashboard"] == before["dashboard"] and value["controller"] == before["controller"]
        with login(ORIGIN, read(ROOT / "access.json")["owner_password"]) as client:
            assert api(client, "config")["config"] == read(ROOT / "dashboard-config.json")["config"]
        dashboard = u.dashboard(u.active()["port"])[0]
        assert command(["exec", dashboard, "cat", "/var/lib/stackarr/runtime-repair-preserve.txt"]) == "Original runtime configuration and backup bytes"


def recorded(case, **extra):
    preserved()
    report = read(ROOT / "cases.json") if (ROOT / "cases.json").exists() else {"cases": []}
    report["cases"].append({"case": case, "passed": True, "main_and_media_preserved": True,
                             "two_app_ids_settings_and_logins_preserved": True, **extra})
    output("cases.json", report)
    print("Runtime/storage acceptance passed: " + case, flush=True)


def prepare():
    ROOT.mkdir(exist_ok=True)
    if (ROOT / "lab-before.json").exists():
        preserved()
        return
    if not (ROOT / "main-before.json").exists():
        output("main-before.json", preservation.main_snapshot())
    media = ROOT / "media"
    if not media.exists():
        shutil.copytree(Path("test-results/docker-optional-maintenance-20261018/media"), media)
        output("media-before.json", hashes(media))
    installation, origin = bootstrap(PACKAGE, ROOT, 29260, 29094, media)
    assert origin == ORIGIN
    invite = command(["compose", "--project-name", installation["project"], "-f", str(STATE / "compose.json"), "exec", "-T", "stackarr", "stackarr", "setup-link"])
    if (ROOT / "access.json").exists():
        password = read(ROOT / "access.json")["owner_password"]
    else:
        password = secrets.token_urlsafe(32)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            page.goto(invite)
            page.get_by_label("Create a password", exact=True).fill(password)
            page.get_by_role("button", name="Continue to setup", exact=False).click()
            expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()
            browser.close()
        output("access.json", {"owner_password": password, "dashboard": origin})
    with login(origin, password) as client:
        existing = next((row for row in api(client, "deployments")["operations"] if set(row["apps"]) == {"sonarr", "radarr"}), None)
        if existing:
            identity = existing["id"]
            if existing["state"] == "failed":
                api(client, "deployments/" + identity + "/resume", {}, status=202)
                wait_job(client, identity, installation=True)
            else:
                assert existing["state"] == "needs-setup"
        else:
            draft = api(client, "onboarding")
            api(client, "onboarding", {"revision": draft["revision"], "draft": {"step": 2, "apps": ["sonarr", "radarr"],
                "port_mode": "custom", "choices": {"sonarr": {"mode": "install", "port": 43300}, "radarr": {"mode": "install", "port": 43301}},
                "data_root": str(media), "folder_root": 0}}, method="PUT")
            reviewed = api(client, "deployments/review", {})
            identity = api(client, "deployments/install", {"review_token": reviewed["review_token"]}, status=202)["id"]
            wait_job(client, identity, installation=True)
        result = api(client, "deployments/" + identity + "/finish-connecting", {})
        assert {row["state"] for row in result["apps"]} == {"connected"}
        output("dashboard-config.json", api(client, "config"))
    service = host()
    payload = load_receipt(service, identity)
    u = updater()
    dashboard = u.dashboard(installation["port"])[0]
    command(["exec", dashboard, "python", "-c", "from pathlib import Path; Path('/var/lib/stackarr/runtime-repair-preserve.txt').write_text('Original runtime configuration and backup bytes')"])
    output("lab-before.json", {"deployment": identity, "installation": installation,
        "apps": {key: inspect_container(service, identity, payload, key)["Id"] for key in payload["apps"]},
        "protected": {key: Updates(service).protected(payload, key, service.store.secret(key)) for key in payload["apps"]},
        "dashboard": command(["exec", dashboard, "python", "-c", FINGERPRINT + "\nprint(fingerprint('/var/lib/stackarr'))"]), "controller": fingerprint(service.store.root)})
    assert not (STATE / "stackarr-runtime.json").exists()
    preserved(runtime=False)
    print("New packaged two-app runtime repair lab ready; account, generated logins and original media fingerprints recorded.", flush=True)


def browser():
    assert not (STATE / "stackarr-runtime.json").exists(), "First repair must not require a separate status/adoption step."
    with sync_playwright() as playwright:
        chromium = playwright.chromium.launch()
        page = chromium.new_page(viewport={"width": 1440, "height": 1050})
        page.set_default_timeout(180000)
        page.goto(ORIGIN)
        page.get_by_label("Password", exact=True).fill(read(ROOT / "access.json")["owner_password"])
        page.get_by_role("button", name="Sign in", exact=False).click()
        page.get_by_role("button", name="Settings", exact=True).click()
        with page.expect_response(lambda r: r.url.endswith("/api/stackarr-update-review")) as review:
            page.get_by_role("button", name="Review Stackarr repair", exact=True).click()
        assert review.value.status == 200
        expect(page.get_by_role("button", name="Repair Stackarr", exact=True)).to_be_visible()
        page.screenshot(path=str(ROOT / "runtime-repair-browser-review.png"), full_page=True)
        with page.expect_response(lambda r: r.url.endswith("/api/stackarr-update-apply")) as applied:
            page.get_by_role("button", name="Repair Stackarr", exact=True).click()
        assert applied.value.status == 202
        wait(applied.value.json()["id"])
        page.goto(ORIGIN)
        expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()
        page.get_by_role("button", name="Settings", exact=True).click()
        page.get_by_role("button", name="Check Stackarr update status", exact=True).click()
        expect(page.get_by_text("Stackarr runtime repaired", exact=False).first).to_be_visible()
        page.screenshot(path=str(ROOT / "runtime-repair-browser-results.png"), full_page=True)
        chromium.close()
    recorded("packaged-browser-repair", current_session_retained=True, first_review_prepared_verified_runtime=True)


def offline(missing=False):
    u = updater()
    runtime = u.active()
    identity = u.dashboard(runtime["port"])[0]
    stop_controller()
    command(["stop", "--timeout", "60", identity])
    if missing:
        command(["rm", identity])
        write(STATE / "compose.json", {"damaged_test_recipe": True})
    request = ROOT / "repair-request.json"
    write(request, {"state": str(STATE)})
    reviewed = frozen("review", request)
    approval = ROOT / ("approval-" + uuid.uuid4().hex[:8] + ".json")
    write(approval, reviewed)
    result = frozen("apply", approval)
    frozen("apply", approval, status=1)
    wait(result["id"])
    recorded("missing-dashboard-and-damaged-compose" if missing else "offline-dashboard-and-controller", one_use_local_review=True)


@contextmanager
def exclusive(path):
    assert path.resolve().is_relative_to(ROOT)
    path.touch(exist_ok=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateFileW(str(path), 0x80000000 | 0x40000000, 0, None, 3, 0x80, None)
    assert handle != ctypes.c_void_p(-1).value
    try:
        yield
    finally:
        kernel.CloseHandle(handle)
        path.unlink(missing_ok=True)


def native_job(u):
    review = u.review("repair")
    launch = u.launch
    u.launch = lambda *args, **kwargs: None
    try:
        return u.approve(review)["id"]
    finally:
        u.launch = launch


def fault(kind):
    u = updater()
    identity = native_job(u)
    holder = None
    evidence = {}
    original_call, runner = u.docker._call, u.docker.runner
    def capture(args, **kwargs):
        result = runner(args, **kwargs)
        error = (result.stderr or "")
        if isinstance(error, bytes):
            error = error.decode(errors="replace")
        if "No space left on device" in error:
            evidence["actual_enospc"] = True
        if "Read-only file system" in error or "Permission denied" in error:
            evidence["actual_write_denied"] = True
        return result
    def call(args, **kwargs):
        nonlocal holder
        if kind == "full" and args[:2] == ["volume", "create"]:
            value = original_call([*args[:-1], "--opt", "type=tmpfs", "--opt", "device=tmpfs", "--opt", "o=size=64k", args[-1]], **kwargs)
            holder = "stackarr-runtime-storage-proof-" + identity
            image = u.release(u.active()["release"])[1]["image_id"]
            original_call(["run", "-d", "--name", holder, "--network", "none", "--read-only", "--entrypoint", "python",
                "--mount", "type=volume,src=" + args[-1] + ",dst=/volume,readonly", image, "-c", "import time; time.sleep(600)"])
            return value
        if kind == "denied" and "run" in args and "/bin/sh" in args:
            args = [arg + ",readonly" if arg.startswith("type=volume,src=stackarr-self-update-") and arg.endswith("dst=/volume") else arg for arg in args]
        return original_call(args, **kwargs)
    u.docker.runner, u.docker._call = capture, call
    try:
        u.execute(identity)
        result = read(u.home / "jobs" / identity / "job.json")
        assert result["phase"] == "failed-recovered", result.get("failure")
        if holder:
            size = int(command(["exec", holder, "python", "-c", "from pathlib import Path; print(sum(p.stat().st_size for p in Path('/volume').rglob('*') if p.is_file()))"]))
            assert size > 0 and evidence.get("actual_enospc")
            evidence["real_partial_candidate_bytes"] = size
        else:
            assert evidence.get("actual_write_denied")
    finally:
        if holder:
            command(["rm", "-f", holder])
    recorded("actual-candidate-" + kind + "-storage-recovery", **evidence)


def poison(u, runtime):
    assert runtime["volume"] != read(u.home / "jobs" / pending(STATE)["id"] / "job.json")["source"]["volume"]
    identity = u.dashboard(runtime["port"])[0]
    script = "from pathlib import Path; from stackarr.store import Store; s=Store(Path('/var/lib/stackarr')); r,c=s.config(); c.dashboard.page_size=43; s.save(c,r); print('Candidate settings write confirmed')"
    assert command(["exec", identity, "python", "-c", script]) == "Candidate settings write confirmed"


def lock_recovery(crash=False):
    u = updater()
    identity = native_job(u)
    original = u.health
    def health(runtime, expected, checking):
        original(runtime, expected, checking)
        if checking:
            poison(u, runtime)
            output("crash-operation.json" if crash else "locked-operation.json", {"id": identity, "actual_candidate_database_write": True})
            if crash:
                os._exit(77)
            raise DeploymentError("Isolated candidate changed real settings")
    u.health = health
    if crash:
        u.execute(identity)
        raise AssertionError("The crash did not execute")
    with exclusive(STATE / "controller/state/stackarr.db.self-update"):
        u.execute(identity)
        assert read(u.home / "jobs" / identity / "job.json")["phase"] == "needs-recovery"
    assert frozen("start")["passed"]
    wait(identity, "failed-recovered")
    recorded("actual-host-write-denial-and-fresh-recovery", actual_candidate_database_write=True, actual_windows_sharing_violation=True)


def interrupted():
    result = subprocess.run([sys.executable, "-m", "tools.docker_runtime_repair_check", "crash"], timeout=600)
    assert result.returncode == 77
    value = read(ROOT / "crash-operation.json")
    assert pending(STATE)["id"] == value["id"]
    assert frozen("start")["passed"]
    wait(value["id"], "failed-recovered")
    recorded("actual-worker-exit-and-fresh-recovery", actual_candidate_database_write=True, actual_worker_exit=True)


def staging():
    u = updater()
    archive = Path("dist") / (PACKAGE.name + ".zip")
    previous = u.active()
    with exclusive(u.home / "candidate.tmp"):
        try:
            u.admit(archive.resolve())
        except PermissionError:
            pass
        else:
            raise AssertionError("The real host write denial did not execute")
    assert u.active() == previous and not pending(STATE)
    u.admit(archive.resolve())
    recorded("atomic-release-admission-write-denial-and-retry", actual_windows_sharing_violation=True)


def unavailable():
    u = updater()
    original = u.docker.context
    u.docker.context = lambda: (_ for _ in ()).throw(DeploymentError("Open Docker and retry"))
    try:
        try:
            u.review("repair")
        except DeploymentError:
            pass
        else:
            raise AssertionError("Unavailable Docker was not rejected")
    finally:
        u.docker.context = original
    assert not pending(STATE)
    recorded("unavailable-runtime-preflight", boundary_fault_simulation=True, docker_engine_not_stopped=True)


def late_port():
    u = updater()
    identity = native_job(u)
    original = u.up
    occupied = socket.socket()
    occupied.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    bound = False
    def up(runtime, checking=False):
        nonlocal bound
        if checking and not bound:
            occupied.bind(("0.0.0.0", runtime["port"]))
            occupied.listen()
            bound = True
        return original(runtime, checking)
    u.up = up
    try:
        u.execute(identity)
        assert bound and read(u.home / "jobs" / identity / "job.json")["phase"] == "needs-recovery"
    finally:
        occupied.close()
    assert frozen("start")["passed"]
    wait(identity, "failed-recovered")
    recorded("actual-late-dashboard-port-conflict-and-fresh-recovery", actual_exclusive_port_listener=True)


def finalize():
    report = read(ROOT / "cases.json")
    assert len(report["cases"]) == 10 and all(row["passed"] for row in report["cases"])
    preserved()
    u = updater()
    runtime = u.active()
    assert u.release(runtime["release"])[1]["release"] == PACKAGE.name
    manifest = u.release(runtime["release"])[1]
    assert u.controller_probe(runtime)["executable"] == manifest["files"]["StackarrPreview.exe"]
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
    dashboard = command(["ps", "-q", "--no-trunc", "--filter", "name=^/stackarr-plex-lab-bc615eaf1fe6-stackarr-1$"])
    fresh = json.loads(command(["exec", dashboard, "python", "-c", script]))
    assert len(fresh) == 9 and all(fresh.values())
    output("main-authenticated-monitoring.json", fresh)
    cleaned = 0
    for directory in u.home.glob("jobs/*/*"):
        if directory.is_dir() and directory.name.startswith(("candidate-", "checkpoint-", "restore-")):
            assert directory.resolve().is_relative_to(ROOT)
            assert not any(p.is_symlink() or p.is_junction() for p in (directory, *directory.rglob("*")))
            assert read(directory.parent / "job.json")["phase"] in TERMINAL
            shutil.rmtree(directory)
            cleaned += 1
    stop_controller()
    identity = read(ROOT / "lab-before.json")["deployment"]
    command(["compose", "--project-name", "stackarr-owned-" + identity, "-f", str(STATE / "controller/state/deployments" / identity / "compose.json"), "stop", "--timeout", "90"])
    command(["compose", "--project-name", runtime["project"], "-f", str(STATE / "compose.json"), "stop"])
    retained_volumes = set(command(["volume", "ls", "-q"]).splitlines())
    command(["compose", "--project-name", "stackarr-owned-" + identity, "-f", str(STATE / "controller/state/deployments" / identity / "compose.json"), "down"])
    command(["compose", "--project-name", runtime["project"], "-f", str(STATE / "compose.json"), "down"])
    assert retained_volumes == set(command(["volume", "ls", "-q"]).splitlines())
    preservation.OUTPUT = ROOT
    preservation.main_preserved()
    assert hashes(ROOT / "media") == read(ROOT / "media-before.json")
    for port in (runtime["port"], runtime["controller_port"], 43300, 43301):
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", port)) != 0
    output("acceptance.json", {"passed": True, "cases": 10, "package": PACKAGE.name,
        "existing_main_apps_media_settings_preserved": True, "main_media_files": len(read(ROOT / "main-before.json")["media"]),
        "nine_main_integrations_freshly_authenticated": True, "actual_frozen_controller_and_bundled_image": True,
        "lab_apps_settings_logins_media_and_runtime_account_preserved": True, "lab_stopped_with_volumes_keys_and_backups_retained": True,
        "only_this_tasks_temporary_containers_and_networks_removed": True,
        "temporary_plaintext_work_directories_removed": cleaned})
    print("Runtime repair and storage recovery acceptance passed; isolated lab stopped and all existing apps/media preserved.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "browser", "offline", "missing", "denied", "full", "lock", "interrupted", "crash", "staging", "unavailable", "late-port", "finalize"))
    args = parser.parse_args()
    if args.phase in {"denied", "full"}:
        fault(args.phase)
    elif args.phase in {"offline", "missing"}:
        offline(args.phase == "missing")
    elif args.phase in {"lock", "crash"}:
        lock_recovery(args.phase == "crash")
    elif args.phase == "late-port":
        late_port()
    else:
        globals()[args.phase]()
