"""Isolated Docker Desktop Plex walkthrough; no Windows startup or account claim."""

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

from stackarr.controller_enrollment import enroll
from stackarr.docker_runtime import executable, inspect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    delivery = parser.add_mutually_exclusive_group(required=True)
    delivery.add_argument("--image", help="Separately built Stackarr preview image")
    delivery.add_argument("--package", type=Path, help="Extracted Docker preview package; starts without recipient Python")
    parser.add_argument("--port", type=int, default=29100)
    parser.add_argument("--controller-port", type=int, default=29010)
    parser.add_argument("--plex-port", type=int, default=42450)
    parser.add_argument("--keep-running", action="store_true", help="Keep only this lab's dashboard/controller/apps for human Plex setup")
    args = parser.parse_args()
    if args.package and not args.keep_running:
        parser.error("Package acceptance leaves its explicitly owned preview available; use --keep-running")
    image = args.image if args.image else json.loads((args.package / "manifest.json").read_text())["image"]
    runtime = inspect(enabled=True)
    if runtime["state"] != "ready":
        raise SystemExit("Docker is not ready. Open Docker Desktop and check its Linux engine first.")
    for port in (args.port, args.controller_port, args.plex_port):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    root = (Path("test-results") / ("docker-plex-" + uuid.uuid4().hex[:12])).resolve()
    root.mkdir(parents=True)
    media = root / "media"
    media.mkdir()
    sentinel = media / "preserve.txt"
    sentinel.write_text("Synthetic Plex lab sentinel. Keep unchanged.", encoding="utf-8")
    sentinel_hash = hashlib.sha256(sentinel.read_bytes()).hexdigest()
    (root / "runtime.json").write_text(json.dumps(runtime, indent=2), encoding="utf-8")
    controller_root = root / ("package-state/controller" if args.package else "controller")
    enrollment = enroll(controller_root) if not args.package else {"shared": controller_root / "shared"}
    project = "stackarr-plex-lab-" + root.name.removeprefix("docker-plex-")
    origin = f"http://localhost:{args.port}"
    compose = root / "compose.json"
    compose.write_text(json.dumps({"services": {"stackarr": {
        "image": image, "init": True, "read_only": True, "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "ports": [f"127.0.0.1:{args.port}:8787"],
        "environment": {"STACKARR_ORIGIN": origin, "STACKARR_CONTROLLER_SHARED": "/run/stackarr-controller",
                        "STACKARR_CONTROLLER_PORT": str(args.controller_port)},
        "volumes": ["dashboard-state:/var/lib/stackarr", {"type": "bind",
                    "source": str(enrollment["shared"]), "target": "/run/stackarr-controller", "read_only": True}],
        "tmpfs": ["/tmp:rw,noexec,nosuid,size=32m"],
    }}, "volumes": {"dashboard-state": {}}}, indent=2), encoding="utf-8")
    docker = executable()

    def command(arguments, timeout=120):
        result = subprocess.run([docker, *arguments], capture_output=True, text=True,
                                timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if result.returncode:
            raise RuntimeError("A scoped Docker lab operation failed; inspect the retained lab state.")
        return result.stdout.strip()

    base = ["compose", "--project-name", project, "-f", str(compose)]
    before = set(command(["ps", "-q"]).splitlines())
    environment = os.environ.copy()
    environment.update(STACKARR_PORT=str(args.port), STACKARR_CONTROLLER_ROOTS=json.dumps([
        {"path": str(media), "host_path": str(media), "label": "Plex test media"}]))
    log = (root / "controller.log").open("w", encoding="utf-8")
    worker = None
    if args.package:
        bootstrap = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-File",
                        str((args.package / "Start-StackarrPreview.ps1").resolve()),
                        "-StateDirectory", str(root / "package-state"), "-MediaFolder", str(media),
                        "-Port", str(args.port), "-ControllerPort", str(args.controller_port), "-NoBrowser"],
                       capture_output=True, text=True, timeout=240,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        (root / "bootstrap.log").write_text(bootstrap.stdout + bootstrap.stderr, encoding="utf-8")
        if bootstrap.returncode:
            raise RuntimeError("Package startup failed; inspect " + str(root / "bootstrap.log"))
        installation = json.loads((root / "package-state/installation.json").read_text(encoding="utf-8-sig"))
        project = installation["project"]
        compose = root / "package-state/compose.json"
        base = ["compose", "--project-name", project, "-f", str(compose)]
    else:
        worker = subprocess.Popen([sys.executable, "-m", "stackarr.cli", "controller-serve", str(controller_root),
                                   "--port", str(args.controller_port)], env=environment, stdout=log, stderr=log,
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    identity, passed = None, False
    try:
        for _ in range(100):
            if worker and worker.poll() is not None:
                raise RuntimeError("The isolated controller could not start.")
            try:
                with socket.create_connection(("127.0.0.1", args.controller_port), timeout=.2):
                    break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError("The isolated controller did not become ready.")
        command([*base, "up", "-d", "--wait", "--wait-timeout", "120"], timeout=150)
        invitation = command([*base, "exec", "-T", "stackarr", "stackarr", "setup-link"])
        password = secrets.token_urlsafe(24)
        (root / "access.json").write_text(json.dumps({"dashboard": origin, "owner_password": password,
            "plex": f"http://localhost:{args.plex_port}/web", "controller_pid": worker.pid if worker else int((root / "package-state/controller.pid").read_text()),
            "notice": "Private disposable lab credentials. Do not upload or include in release artifacts."}, indent=2), encoding="utf-8")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1200, "height": 900})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(invitation)
            page.get_by_label("Create a password", exact=True).fill(password)
            page.get_by_role("button", name="Continue to setup", exact=False).click()
            page.get_by_role("button", name="Check Docker", exact=True).click()
            expect(page.locator("#setup-runtime-result")).to_contain_text("Docker is ready", timeout=45000)
            page.get_by_role("button", name="Watch my media", exact=True).click()
            page.get_by_label("Port selection", exact=True).select_option("custom")
            page.get_by_label("Plex port", exact=True).fill(str(args.plex_port))
            page.get_by_role("button", name="Save & continue", exact=False).click()
            page.get_by_role("button", name="Choose a folder…", exact=True).click()
            page.get_by_role("button", name="My media folder" if args.package else "Plex test media", exact=True).click()
            page.get_by_role("button", name="Use this folder", exact=True).click()
            page.get_by_role("button", name="Save & continue", exact=False).click()
            page.get_by_role("button", name="Review installation", exact=True).click()
            page.get_by_role("button", name="Download & install these apps", exact=True).click()
            page.get_by_role("heading", name="Apps installed — finish setup", exact=True).or_(
                page.get_by_role("heading", name="Installation needs attention", exact=True)).wait_for(timeout=1200000)
            operations = page.request.get(origin + "/api/deployments").json()["operations"]
            assert len(operations) == 1 and operations[0]["state"] == "needs-setup", "Plex install did not complete"
            identity = operations[0]["id"]
            assert operations[0]["apps"] == ["plex"]
            assert operations[0]["links"] == [{"app": "plex", "url": f"http://localhost:{args.plex_port}/web"}]
            page.get_by_role("button", name="Finish connecting", exact=True).click()
            panel = page.locator("section").filter(has=page.get_by_role("heading", name="Finish connecting your apps", exact=True))
            expect(panel.locator('[role="status"]')).to_contain_text("finish server setup", timeout=45000)
            config = page.request.get(origin + "/api/config").json()
            assert "plex" not in config.get("credentials", [])
            page.reload()
            page.get_by_role("heading", name="Set up your media server.", exact=True).or_(
                page.get_by_role("button", name="Resume setup", exact=True)).or_(
                page.get_by_role("heading", name="Your apps are installed.", exact=True)).first.wait_for()
            if page.get_by_role("button", name="Resume setup", exact=True).count():
                page.get_by_role("button", name="Resume setup", exact=True).click()
            expect(page.get_by_role("heading", name="Apps installed — finish setup", exact=True)).to_be_visible()
            page.screenshot(path=str(root / "plex-setup.png"), full_page=True)
            assert not errors, errors
            browser.close()
        with httpx.Client(trust_env=False, timeout=10, follow_redirects=True) as client:
            response = client.get(f"http://localhost:{args.plex_port}/web")
            assert response.status_code == 200 and "text/html" in response.headers.get("content-type", "")
        payload_path = controller_root / "state" / "deployments" / identity / "compose.json"
        owned = json.loads(payload_path.read_text(encoding="utf-8"))
        assert set(owned["services"]) == {"plex"}
        assert next(m for m in owned["services"]["plex"]["volumes"] if m["target"] == "/data")["read_only"]
        assert hashlib.sha256(sentinel.read_bytes()).hexdigest() == sentinel_hash
        assert before <= set(command(["ps", "-q"]).splitlines()), "An unrelated running container changed"
        (root / "report.json").write_text(json.dumps({"passed": True,
            "scope": "Docker-only browser install of unclaimed Plex; account claim, playback, LAN and Windows startup remain unverified",
            "dashboard": origin, "plex": f"http://localhost:{args.plex_port}/web", "project": project,
            "deployment": identity, "image": command(["image", "inspect", image, "--format", "{{.Id}}"]),
            "packaged_startup_without_python": bool(args.package),
            "checks": ["host Docker readiness through private controller", "browser-reviewed Plex-only install",
                       "approved host folder", "correct Plex Web link", "unclaimed account guidance",
                       "saved progress after reload", "read-only media mount", "sentinel and unrelated containers preserved"],
            "kept_running": args.keep_running}, indent=2), encoding="utf-8")
        passed = True
        print("Docker Plex walkthrough passed; evidence: " + str(root / "report.json"))
    finally:
        if not args.keep_running:
            if worker:
                worker.terminate()
                worker.wait(timeout=15)
            if passed and identity:
                app_compose = controller_root / "state" / "deployments" / identity / "compose.json"
                command(["compose", "--project-name", "stackarr-owned-" + identity, "-f", str(app_compose), "stop"])
                command([*base, "stop"])
        log.close()


if __name__ == "__main__":
    main()
