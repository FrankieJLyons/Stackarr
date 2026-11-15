"""Standalone, read-only Windows readiness; no account or installation state."""

import json
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path

DOCKER_GUIDE = "https://docs.docker.com/desktop/setup/install/windows-install/"
REQUIREMENTS_REVIEWED = "2026-10-19"
MODES = ("install", "connect")
MIN_MEMORY = 8_000_000_000
SPACE_NOTICE = 10 * 1024**3  # Planning reminder for the setup drive, not an image/media estimate.

# Return only the fields needed by this check. Never enumerate accounts or apps.
WINDOWS_QUERY = r"""
$ErrorActionPreference = 'Stop'
$os = Get-CimInstance Win32_OperatingSystem
$computer = Get-CimInstance Win32_ComputerSystem
$cpu = @(Get-CimInstance Win32_Processor)
[ordered]@{
    build = [int]$os.BuildNumber
    workstation = $os.ProductType -eq 1
    memory = [long]$computer.TotalPhysicalMemory
    hypervisor = [bool]$computer.HypervisorPresent
    virtualization = @($cpu | Where-Object { $_.VirtualizationFirmwareEnabled -eq $true }).Count -eq $cpu.Count -and $cpu.Count -gt 0
} | ConvertTo-Json -Compress
"""


def windows_facts(*, runner=None):
    """Bounded local CIM inventory. Unknown facts never become successful checks."""
    if platform.system() != "Windows":
        return {"windows": False}
    facts = {"windows": True, "architecture": os.environ.get("PROCESSOR_ARCHITEW6432")
             or os.environ.get("PROCESSOR_ARCHITECTURE") or platform.machine()}
    system = os.environ.get("SystemRoot")
    if not system or not Path(system).is_absolute():
        return facts
    powershell = Path(system) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    try:
        response = (runner or subprocess.run)(
            [str(powershell), "-NoProfile", "-NonInteractive", "-Command", WINDOWS_QUERY],
            env={**os.environ, "PSModulePath": str(Path(system) / "System32/WindowsPowerShell/v1.0/Modules")},
            capture_output=True, text=True, timeout=12,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if response.returncode or len(response.stdout) > 4096:
            return facts
        data = json.loads(response.stdout)
        if not isinstance(data, dict):
            return facts
        for key in ("build", "memory"):
            if type(data.get(key)) is int and data[key] > 0:
                facts[key] = data[key]
        for key in ("workstation", "hypervisor", "virtualization"):
            if type(data.get(key)) is bool:
                facts[key] = data[key]
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return facts


def setup_space():
    """Observe the existing per-user setup drive, without creating a directory."""
    base = os.environ.get("LOCALAPPDATA")
    if not base or not Path(base).is_absolute():
        return None
    try:
        return shutil.disk_usage(base).free
    except OSError:
        return None


def inspect(mode="install", *, facts_reader=None, space_reader=None, runtime_reader=None):
    if mode not in MODES:
        raise ValueError("Choose install or connect")
    result = {"schema": 1, "mode": mode, "checked_at": time.time(), "state": "attention",
              "checks": [], "requirements_reviewed": REQUIREMENTS_REVIEWED,
              "scope": "prerequisites-only", "installation_started": False}

    def add(key, title, state, detail, action=None):
        row = {"id": key, "title": title, "state": state, "detail": detail}
        if action:
            row["action"] = action
        result["checks"].append(row)

    if mode == "connect":
        add("existing", "Existing apps", "pass", "Connecting apps you already run does not require a local Docker engine or media folder.")
        result.update(state="ready", title="Ready to connect existing apps",
                      next_step="Open the local Stackarr launcher and choose your existing apps. Their addresses and logins are checked during connection setup.")
        return result

    facts = (facts_reader or windows_facts)()
    windows = facts.get("windows") is True
    build = facts.get("build")
    if not windows:
        add("windows", "Windows version", "block", "This installation preview is for Windows 11 x64. Use a supported Windows computer for this check.")
    elif facts.get("workstation") is False or (type(build) is int and build < 22631):
        add("windows", "Windows version", "block", "Use Windows 11 version 23H2 or later on a desktop PC. Windows Server is outside this preview.",
            {"label": "Review Docker requirements", "url": DOCKER_GUIDE})
    elif type(build) is int and facts.get("workstation") is True:
        add("windows", "Windows version", "pass", f"Windows desktop build {build}. Keep Windows within Microsoft's supported servicing period.")
    else:
        add("windows", "Windows version", "unknown", "Windows details could not be checked. Check your version in Settings > System > About, then try again.")

    architecture = str(facts.get("architecture", "")).lower()
    if not windows:
        add("architecture", "Processor", "skip", "Check this on the Windows installation computer.")
    elif architecture in ("amd64", "x86_64"):
        add("architecture", "Processor", "pass", "This computer uses an x64 processor.")
    else:
        add("architecture", "Processor", "block" if architecture else "unknown", "This preview needs an x64 processor. ARM and 32-bit computers are outside its tested scope.")

    memory = facts.get("memory")
    if type(memory) is int and memory > 0:
        add("memory", "Memory", "pass" if memory >= MIN_MEMORY else "block",
            f"{memory / 1024**3:.1f} GB of physical memory. Docker requires at least 8 GB; your selected apps may need more.")
    else:
        add("memory", "Memory", "unknown", "Memory could not be checked. Docker requires at least 8 GB of system RAM.")

    # Do not invoke a local runtime from the wrong platform/architecture.
    allowed = windows and architecture in ("amd64", "x86_64")
    runtime = {"checks": [], "state": "not-checked"}
    if allowed:
        try:
            if runtime_reader is None:
                from .docker_runtime import inspect as runtime_reader
            runtime = runtime_reader(enabled=True)
        except Exception:
            # No command line, raw stderr, local paths or engine endpoint is exposed.
            runtime = {"checks": [{"check": "docker", "ok": False,
                                    "detail": "Docker could not be checked. Reopen this checker and try again."}]}

    engine_ready = any(row.get("check") == "engine" and row.get("ok") is True
                       for row in runtime.get("checks", []))
    virtual = facts.get("hypervisor") is True or facts.get("virtualization") is True
    if virtual or engine_ready:
        add("virtualization", "Virtualization", "pass", "Virtualization is available." if virtual
            else "The running local Linux engine confirms virtualization is available.")
    else:
        add("virtualization", "Virtualization", "unknown", "Virtualization could not be confirmed. In Task Manager > Performance > CPU, check that Virtualization is enabled. Follow Docker's setup guide if it is disabled.",
            {"label": "View setup requirements", "url": DOCKER_GUIDE})

    free = (space_reader or setup_space)() if windows else None
    if type(free) is int and free >= 0:
        add("space", "Setup drive space", "pass" if free >= SPACE_NOTICE else "note",
            f"{free / 1024**3:.1f} GB free on the local setup drive. "
            + ("Review available space before continuing. " if free < SPACE_NOTICE else "")
            + "Docker's app storage and your media folder need separate space checks after you choose apps and folders.")
    else:
        add("space", "Setup drive space", "note", "Setup drive space could not be read. Check free space in File Explorer; app storage and media are checked after your choices.")

    titles = {"docker": "Docker Desktop", "context": "Docker connection", "compose": "Docker Compose",
              "engine": "Container engine", "network capacity": "Docker network capacity", "computer": "Docker connection",
              "architecture": "Docker processor"}
    if allowed:
        for row in runtime.get("checks", []):
            key = row.get("check")
            if key in titles:
                state = "pass" if row.get("ok") is True else "block"
                if key == "network capacity" and runtime.get("network_capacity", {}).get("state") in ("low", "unknown"):
                    state = "note"
                add("runtime-" + key.replace(" ", "-"), titles[key], state,
                    row["detail"], None if row.get("ok") is True else {"label": "Open Docker setup guide", "url": DOCKER_GUIDE})
        if not runtime.get("checks"):
            add("runtime", "Docker Desktop", "unknown", "Docker checks did not complete. Reopen the checker on the installation computer.")
    else:
        add("runtime", "Docker Desktop", "skip", "Docker can be checked after the Windows and processor requirements are met.")

    blocked = any(row["state"] in ("block", "unknown") for row in result["checks"])
    ready = not blocked and runtime.get("state") == "ready"
    result.update(state="ready" if ready else "attention",
                  title="Ready for the next setup step" if ready else "A few things need attention",
                  next_step="Open your Stackarr preview package to choose apps and folders, then review installation. This check does not verify app connections, playback or startup after reboot." if ready
                  else "Follow the steps shown below, then choose Check again. If an installer asks you to restart Windows, save your work, restart when convenient and reopen this checker.")
    if not ready:
        order = ("windows", "architecture", "memory", "runtime-docker", "runtime-context",
                 "runtime-computer", "runtime-compose", "runtime-engine", "runtime-network-capacity", "virtualization")
        issues = [row for row in result["checks"] if row["state"] in ("block", "unknown")]
        issues.sort(key=lambda row: order.index(row["id"]) if row["id"] in order else len(order))
        if issues:
            issue = issues[0]
            result.update(title=issue["title"] + " needs attention", next_step=issue["detail"] + " Then choose Check again.")
            if issue.get("action"):
                result["primary_action"] = issue["action"]
            if issue["id"] == "runtime-docker" and runtime.get("guide") == DOCKER_GUIDE:
                result.update(title="Install Docker Desktop to continue",
                              next_step="Use Docker's official guide to install Docker Desktop. Open Docker Desktop, complete its setup prompts, then choose Check again. If installation asks for a restart, save your work and reopen this checker afterwards.",
                              primary_action={"label": "Get Docker Desktop", "url": DOCKER_GUIDE})
    return result
