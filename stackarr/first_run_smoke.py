"""Frozen readiness smoke checks using synthetic facts and local HTTP only."""

import contextlib
import hashlib
import http.client
import json
import sys
import tempfile
import threading
from pathlib import Path

from .first_run import DOCKER_GUIDE, inspect
from .first_run_server import ReadinessServer, assets


def run(path):
    checks = []
    try:
        for name in ("index.html", "readiness.css", "readiness.js"):
            if not (assets() / name).is_file() or not (assets() / name).read_bytes():
                raise ValueError("Asset unavailable")
            checks.append("bundled-" + name)
        facts = {"windows": True, "architecture": "AMD64", "build": 26100,
                 "workstation": True, "memory": 16 * 1024**3, "hypervisor": True}

        def missing(mode):
            return inspect(mode, facts_reader=lambda: facts, space_reader=lambda: 30 * 1024**3,
                           runtime_reader=lambda **_: {"state": "needs-attention", "guide": DOCKER_GUIDE, "checks": [
                               {"check": "docker", "ok": False, "detail": "Docker was not found. Install Docker using the official guide, then reopen Stackarr."}]})

        with ReadinessServer(missing) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                def request(method, route, mode=None, authorized=True):
                    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                    body = json.dumps({"mode": mode}) if mode else None
                    headers = {"Origin": server.origin, "Content-Type": "application/json"}
                    if authorized:
                        headers["X-Readiness-Key"] = server.key
                    try:
                        connection.request(method, route, body, headers)
                        response = connection.getresponse()
                        return response.status, response.read()
                    finally:
                        connection.close()

                for route in ("/", "/readiness.css", "/readiness.js"):
                    status, body = request("GET", route)
                    if status != 200 or not body or server.key.encode() in body:
                        raise ValueError("Page check failed")
                    checks.append("served-" + (route.strip("/") or "page"))
                status, body = request("POST", "/api/check", "install")
                result = json.loads(body)
                if status != 200 or result["state"] != "attention" or not any(
                    row["id"] == "runtime-docker" and row["action"] for row in result["checks"]
                ):
                    raise ValueError("Missing-Docker check failed")
                checks.append("missing-docker-guidance")
                status, body = request("POST", "/api/check", "connect")
                if status != 200 or json.loads(body)["state"] != "ready":
                    raise ValueError("Connect check failed")
                checks.append("connect-without-docker")
                status, _ = request("POST", "/api/check", "install", authorized=False)
                if status != 403:
                    raise ValueError("Authorization check failed")
                checks.append("unauthorized-check-denied")
            finally:
                server.shutdown()
                worker.join(timeout=3)
        from .first_run_docker import RELEASE, DockerSetup, SetupError

        payload = b"Frozen synthetic prerequisite; never executed"
        original = dict(RELEASE)
        calls = []
        try:
            RELEASE["sha256"] = hashlib.sha256(payload).hexdigest()
            with tempfile.TemporaryDirectory(prefix="stackarr-readiness-smoke-") as temporary:
                def download(path, update, cancelled):
                    path.write_bytes(payload)
                    update(len(payload))
                    return True

                setup = DockerSetup(Path(temporary), exists=lambda: False, downloader=download,
                                    signer=lambda _: calls.append("signature"),
                                    launcher=lambda _: calls.append("installer") or 0,
                                    locker=lambda _: contextlib.nullcontext())
                review = setup.review(missing("install"))
                setup.start(review["review_id"], missing("install"))
                setup.worker.join(timeout=5)
                if setup.worker.is_alive() or calls != ["signature", "installer"] or setup.status()["phase"] != "complete":
                    raise ValueError("Prerequisite sequence failed")
                checks.append("reviewed-prerequisite-verification-and-install-sequence")
                if DockerSetup(Path(temporary)).status()["phase"] != "complete":
                    raise ValueError("Prerequisite outcome was not retained")
                checks.append("retained-prerequisite-outcome")
                setup.exists = lambda: True
                try:
                    setup.review(missing("install"))
                except SetupError:
                    checks.append("existing-docker-installation-refused")
                else:
                    raise ValueError("Existing Docker was not protected")
        finally:
            RELEASE.clear()
            RELEASE.update(original)
        result = {"passed": True, "frozen": bool(getattr(sys, "frozen", False)), "checks": checks,
                  "docker_contacted": False, "installation_started": False}
    except Exception:
        result = {"passed": False, "frozen": bool(getattr(sys, "frozen", False)), "checks": checks,
                  "message": "The isolated readiness smoke checks did not finish."}
    try:
        with Path(path).open("x", encoding="utf-8") as output:
            json.dump(result, output, indent=2)
    except OSError:
        return 2
    return 0 if result["passed"] else 1
