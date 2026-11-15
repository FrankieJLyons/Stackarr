"""Explicit local-host preflight. No installs, downloads, or credential discovery."""

import hashlib
import os
import subprocess
import time
from pathlib import Path

from .docker_runtime import executable as docker_executable
from .installer import preflight


def report(config, *, enabled=False, runner=None):
    runner = runner or subprocess.run
    fingerprint = hashlib.sha256(config.model_dump_json().encode()).hexdigest()
    result = {"schema": 1, "configuration": fingerprint, "checked_at": time.time(),
              "scope": "unverified", "checks": [], "preflight_passed": False,
              "installation_started": False,
              "limitations": ["App identity, container permissions, LAN access and startup before sign-in require separate tests."]}

    def stop(detail):
        result["checks"] = [{"check": "host scope", "ok": False, "detail": detail}]
        return result

    selected = [app for app in config.integrations.values() if app.enabled]
    if selected and all(app.mode == "connect" for app in selected):
        result.update(scope="connection-only", preflight_passed=True,
                      checks=[{"check": "installation prerequisites", "ok": True,
                               "detail": "No new apps selected. Local Docker, installation ports and media folders are not needed for these connections."}],
                      limitations=["Existing app addresses and credentials still need connection tests in Apps. No host or application identity was verified."])
        return result

    if not enabled:
        return stop("Host checks are not enabled here. Run the local checker on the installation computer.")
    if Path("/.dockerenv").exists() or Path("/run/.containerenv").exists():
        return stop("Stackarr is inside a container. Its folders and ports cannot certify the installation host.")
    if os.environ.get("DOCKER_HOST"):
        return stop("An overridden Docker endpoint is configured. Use a verified local Docker context for host checks.")
    executable = docker_executable()
    if executable:
        try:
            context = runner([executable, "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
                             capture_output=True, text=True, timeout=10,
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            endpoint = context.stdout.strip()
            local = endpoint.startswith("unix:///") or endpoint.startswith("npipe:////./pipe/")
            if context.returncode != 0 or not local:
                return stop("Docker context is remote or unverified. Select a local context on the installation computer.")
        except (OSError, subprocess.TimeoutExpired):
            return stop("Docker context could not be checked. Start the local runtime and try again.")
    result["scope"] = "local-process-and-local-docker-context"
    try:
        result["checks"] = preflight(config)
    except OSError:
        return stop("A host resource could not be inspected. Check folder permissions and retry.")
    result["preflight_passed"] = bool(result["checks"]) and all(c["ok"] for c in result["checks"])
    return result
