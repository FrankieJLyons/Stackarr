"""Read-only local Docker checks shared by the packaged launcher and setup UI."""

import json
import os
import platform
import re
import shutil
import subprocess
import time
from pathlib import Path

GUIDE = "https://docs.docker.com/desktop/setup/install/windows-install/"


def executable(command="docker"):
    found = shutil.which(command)
    if found or command != "docker" or platform.system() != "Windows":
        return found
    # Docker's per-user installer need not update an already running process's PATH.
    for variable, relative in (
        ("LOCALAPPDATA", "Programs/DockerDesktop/resources/bin/docker.exe"),
        ("ProgramFiles", "Docker/Docker/resources/bin/docker.exe"),
    ):
        base = os.environ.get(variable)
        if base and Path(base).is_absolute():
            candidate = Path(base) / relative
            if candidate.is_file():
                return str(candidate)
    return None


def inspect(*, enabled=False, runner=None):
    """Never start Docker, contact a remote engine or modify containers/settings."""
    result = {"schema": 1, "checked_at": time.time(), "state": "not-checked",
              "checks": [], "installation_started": False,
              "scope": "local-runtime-only",
              "notice": "Storage, app connections, playback and startup before sign-in need separate checks."}

    def add(name, ok, detail):
        result["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        result["state"] = "needs-attention"

    if not enabled:
        result["notice"] = "Open Stackarr on the installation computer to check Docker."
        return result
    if Path("/.dockerenv").exists() or Path("/run/.containerenv").exists() or os.environ.get("DOCKER_HOST"):
        add("computer", False, "Use the local launcher with a local Docker context; an overridden or container endpoint cannot check this computer.")
        return result
    if platform.machine().lower() not in ("amd64", "x86_64"):
        add("architecture", False, "This installer currently requires an x64 computer.")
        return result
    docker = executable()
    if not docker:
        add("docker", False, "Docker was not found. Install Docker using the official guide, then reopen Stackarr.")
        result["guide"] = GUIDE
        return result
    add("docker", True, "Docker is installed.")
    run = runner or subprocess.run

    def command(arguments, limit=4096):
        response = run([docker, *arguments], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=8,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if response.returncode or len(response.stdout) > limit:
            raise ValueError("Docker check failed")
        return response.stdout.strip()

    try:
        context = command(["context", "show"])
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", context):
            raise ValueError("Unsupported context")
        endpoint = command(["context", "inspect", context, "--format", "{{.Endpoints.docker.Host}}"])
        if not endpoint.startswith(("unix:///", "npipe:////./pipe/")):
            raise ValueError("Nonlocal endpoint")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        add("context", False, "Select a local Docker context on this computer, then check again. No engine was contacted.")
        return result
    add("context", True, "The selected Docker connection is local.")
    try:
        version = command(["--context", context, "compose", "version", "--short"])
        supported = bool(re.fullmatch(r"v?(?:2|5)\.\d+\.\d+(?:[-+][\w.-]+)?", version))
        add("compose", supported, "Compose " + version if supported else "Update Docker to a supported Compose v2 or v5 release.")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        add("compose", False, "Docker Compose is unavailable. Repair or update Docker, then check again.")
    try:
        engine = json.loads(command(["--context", context, "info", "--format",
                                     '{"OSType":{{json .OSType}},"Architecture":{{json .Architecture}}}']))
        if not isinstance(engine, dict):
            raise ValueError("Invalid engine info")
        if engine.get("OSType") != "linux":
            add("engine", False, "Switch Docker to Linux containers, wait for it to start, then check again.")
        elif engine.get("Architecture", "").lower() not in ("amd64", "x86_64"):
            add("engine", False, "The selected Docker engine must support Linux x64 apps.")
        else:
            add("engine", True, "The Linux x64 container engine is running.")
    except (OSError, ValueError, AttributeError, subprocess.TimeoutExpired):
        add("engine", False, "Docker's engine is not ready. Open Docker Desktop, wait until its engine is running, then check again.")
    if any(row["check"] == "engine" and row["ok"] for row in result["checks"]):
        from .docker_networks import inspect as networks

        capacity = networks(lambda args: command(["--context", context, *args], limit=262144))
        result["network_capacity"] = capacity
        add("network capacity", capacity["state"] != "exhausted", capacity["detail"])
    if all(check["ok"] for check in result["checks"]):
        result["state"] = "ready"
    return result


def write_report(path):
    result = inspect(enabled=True)
    # Do not overwrite an earlier observation or follow an existing report link.
    with Path(path).open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2)
    return 0 if result["state"] == "ready" else 1
