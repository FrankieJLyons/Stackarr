"""Local-only Compose runner; never imported as a host controller by the web service."""

import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path

from .config import CATALOG, Config, container_port
from .docker_runtime import executable as docker_executable


def compose_plan(config: Config):
    services = {}
    volumes = {}
    steps = ["Build the Stackarr image from this checkout before applying the plan."]
    for key, app in config.integrations.items():
        if not app.enabled or app.mode != "install":
            continue
        info = CATALOG[key]
        service = {
            "image": info["image"],
            "restart": "unless-stopped",
            "ports": [
                {
                    "target": container_port(key, app),
                    "published": str(app.port or info["port"]),
                    "host_ip": "127.0.0.1",
                    "protocol": "tcp",
                }
            ],
            "volumes": [{"type": "volume", "source": key + "-config", "target": info["config"]}],
            "security_opt": ["no-new-privileges:true"],
            "environment": {"TZ": "Etc/UTC"},
        }
        volumes[key + "-config"] = {}
        if key == "qbittorrent":
            service["environment"]["WEBUI_PORT"] = str(container_port(key, app))
        if key == "seerr":
            service.update(init=True, cap_drop=["ALL"])
            service["environment"]["LOG_LEVEL"] = "info"
        if key == "kuma":
            service["environment"]["UPTIME_KUMA_DB_TYPE"] = "sqlite"
        if key in ("sonarr", "radarr", "prowlarr", "qbittorrent", "cleanuparr", "tautulli"):
            service["environment"].update(
                PUID=str(config.storage.uid), PGID=str(config.storage.gid), UMASK="022"
            )
        if key == "plex":
            service["environment"].update(PLEX_UID=str(config.storage.uid), PLEX_GID=str(config.storage.gid))
        if key in ("plex", "sonarr", "radarr", "qbittorrent"):
            service["volumes"].append(
                {
                    "type": "bind",
                    "source": config.storage.data_root,
                    "target": "/data",
                    "read_only": key == "plex",
                    "bind": {"create_host_path": False},
                }
            )
        services[key] = service
        steps.append(f"{info['name']}: open its local port and complete first-run authentication.")
    if "plex" in services:
        steps.append("Plex: sign in and claim your server manually; choose libraries under /data/media.")
    if "prowlarr" in services:
        steps.append("Prowlarr: choose your own legal indexers; none are preselected.")
    if "cleanuparr" in services:
        steps.append("Companions: review safe setup in Apps. Cleanuparr stays in dry-run with automatic cleanup disabled and no media mounts.")
    if "seerr" in services:
        steps.append("Seerr: complete its setup, choose your media server and Arr connections, then choose Finish connecting in Stackarr. Preview supported Arr connections; manage requests and permissions in Seerr.")
    steps.append(
        "Add API keys in Stackarr Apps. Review supported app-to-app connections there before applying changes."
    )
    for service in services.values():
        service["networks"] = ["control"]
    compose = {
        "services": services,
        "volumes": volumes,
        "networks": {"control": {"external": True, "name": "stackarr-control"}},
    }
    return {
        "compose": compose,
        "human_steps": steps,
        "experimental": True,
        "warning": "App image tags are upstream defaults. Resolve and review immutable digests before a reproducible release.",
    }


def preflight(config, docker="docker", check_ports=True):
    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    machine = platform.machine().lower()
    add("architecture", machine in ("amd64", "x86_64", "aarch64", "arm64"), machine)
    executable = docker_executable(docker)
    add("docker", executable is not None, "Docker is required; install it using the official platform guide.")
    if executable:
        for name, arguments in (
            ("compose", ["compose", "version", "--short"]),
            ("daemon", ["info", "--format", "{{.OSType}}"]),
        ):
            try:
                result = subprocess.run([executable, *arguments], capture_output=True, text=True, timeout=15,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                add(
                    name,
                    result.returncode == 0 and (
                        result.stdout.strip() == "linux" if name == "daemon"
                        else bool(re.fullmatch(r"v?(?:2|5)\.\d+\.\d+(?:[-+][\w.-]+)?", result.stdout.strip()))
                    ),
                    "Requires a running Linux container engine and supported Compose v2 or v5.",
                )
            except (OSError, subprocess.TimeoutExpired):
                add(name, False, "Docker did not respond within 15 seconds.")
    installed = {k: v for k, v in config.integrations.items() if v.enabled and v.mode == "install"}
    needs_storage = any(k in installed for k in ("plex", "sonarr", "radarr", "qbittorrent"))
    if needs_storage:
        path = Path(config.storage.data_root)
        valid = bool(config.storage.data_root) and path.is_absolute() and path.is_dir()
        add(
            "storage",
            valid,
            "Choose an existing absolute host data folder. This check creates nothing; the wizard separately reviews missing app folders.",
        )
        if valid:
            writable = os.access(path, os.R_OK | os.W_OK | os.X_OK)
            add(
                "permissions",
                writable,
                "Host account access check only; container UID/GID access must also be verified.",
            )
            free = shutil.disk_usage(path).free / (1024**3)
            add("space", free >= config.storage.minimum_free_gb, f"{free:.1f} GiB available")
    if check_ports:
        for key, app in installed.items():
            port = app.port or CATALOG[key]["port"]
            try:
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", port))
                add(key + " port", True, str(port))
            except OSError:
                add(key + " port", False, f"Port {port} is in use; choose another port or connect-only mode.")
    if "plex" in installed and machine in ("aarch64", "arm64"):
        add(
            "plex image architecture",
            False,
            "Official Plex image architecture is not verified here; use connect-only on ARM64.",
        )
    return checks


class Installer:
    def __init__(self, directory: Path, runner=subprocess.run):
        self.directory = directory.resolve()
        self.runner = runner

    def _project(self):
        return "stackarr-" + hashlib.sha256(str(self.directory).encode()).hexdigest()[:12]

    @staticmethod
    def _digest(plan):
        return hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _read(self, name):
        path = self.directory / name
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError("Installation files must not be filesystem links")
        return json.loads(path.read_text(encoding="utf-8"))

    def _owned(self):
        state = self._read("stackarr-install.json")
        if state.get("owner") != "stackarr-v1" or state.get("project") != self._project():
            raise ValueError("Installation ownership check failed")
        return state

    def _verified(self, state, previous=False):
        name = "previous" if previous else "current"
        receipt = state.get(name)
        if not receipt:
            raise ValueError("No verified deployment receipt. Prepare and review a fresh plan first.")
        plan = self._read("compose.previous.json" if previous else "compose.json")
        expected = compose_plan(Config.model_validate(receipt["config"]))["compose"]
        if plan != expected or self._digest(plan) != receipt["sha256"]:
            raise ValueError("Deployment plan changed. Prepare and review it again before continuing.")
        return plan

    def _write(self, name, data):
        target = self.directory / name
        temporary = target.with_suffix(".tmp")
        if target.is_symlink() or temporary.exists() or temporary.is_symlink():
            raise ValueError("Unexpected linked or temporary installation file; inspect the directory before retrying.")
        temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(temporary, target)

    def prepare(self, config):
        plan = compose_plan(config)["compose"]
        if not plan["services"]:
            raise ValueError(
                "No installation apps selected. Connect-only configurations need no app deployment."
            )
        self.directory.mkdir(parents=True, exist_ok=True)
        marker = self.directory / "stackarr-install.json"
        if not marker.exists() and any(self.directory.iterdir()):
            raise ValueError("Choose an empty install directory; existing files will not be overwritten.")
        if marker.exists():
            state = self._owned()
            previous = self.directory / "compose.json"
            if previous.exists():
                self._write("compose.previous.json", self._verified(state))
                state["previous"] = state["current"]
        else:
            project = self._project()
            state = {"owner": "stackarr-v1", "project": project, "stage": "prepared"}
        portable = config.model_dump()
        portable["maintenance"]["notification_url"] = ""
        portable["maintenance"]["notifications_enabled"] = False
        state["current"] = {"config": portable, "sha256": self._digest(plan),
                            "images": {key: service["image"] for key, service in plan["services"].items()},
                            "adapter_schema": 1}
        self._write("compose.json", plan)
        self._write("stackarr-install.json", state | {"stage": "prepared", "updated": time.time()})
        return state

    def run(self, action: str):
        if action not in ("apply", "stop", "rollback"):
            raise ValueError("Unsupported action")
        state = self._owned()
        expected = self._project()
        filename = "compose.previous.json" if action == "rollback" else "compose.json"
        if not (self.directory / filename).is_file():
            raise ValueError("No previous plan is available for rollback")
        self._verified(state, previous=action == "rollback")
        # No shell, arbitrary command arguments, pruning, volume deletion or other project access.
        base = ["docker", "compose", "--project-name", expected, "-f", str(self.directory / filename)]
        try:
            check = self.runner([*base, "config", "--quiet"], capture_output=True, timeout=30)
            if check.returncode:
                raise ValueError("Compose rejected the plan; check its paths and image definitions.")
            arguments = (
                ["down"]
                if action == "stop"
                else ["up", "-d", "--wait", "--wait-timeout", "180"]
            )
            result = self.runner([*base, *arguments], capture_output=True, timeout=600)
            if result.returncode:
                raise ValueError(
                    "Compose failed. Inspect this project's logs, correct the issue, then resume apply."
                )
            if action == "rollback":
                self._write("compose.json", self._read(filename))
                state["current"] = state["previous"]
            self._write(
                "stackarr-install.json", state | {"stage": action + "-complete", "updated": time.time()}
            )
        except (OSError, subprocess.TimeoutExpired, ValueError):
            self._write(
                "stackarr-install.json", state | {"stage": action + "-failed", "updated": time.time()}
            )
            raise
