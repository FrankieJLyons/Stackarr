"""Read-only comparison of owned containers with their saved installation receipt."""

import json
import os
import re
import time

from .config import CATALOG
from .deployment import DeploymentError
from .docker_names import app_project


def host_path(value):
    # Docker Desktop can return either Windows paths or its Linux host-mount spelling.
    if os.name == "nt" and (match := re.fullmatch(r"/(?:run/desktop/mnt/host|host_mnt)/([a-zA-Z])/(.*)", value)):
        value = match[1] + ":/" + match[2]
    return os.path.normcase(os.path.normpath(value))


def differences(info, project, key, service):
    changed = []
    labels = info.get("Config", {}).get("Labels") or {}
    if labels.get("com.docker.compose.project") != project or labels.get("com.docker.compose.service") != key:
        changed.append("container ownership")
    if info.get("Config", {}).get("Image") != service["image"]:
        changed.append("image")
    mounts = {mount["Destination"]: mount for mount in info.get("Mounts", [])}
    config = mounts.get(CATALOG[key]["config"], {})
    if config.get("Type") != "volume" or config.get("Name") != project + "_" + key + "-config":
        changed.append("configuration volume")
    reviewed_binds = {mount["target"]: mount for mount in service["volumes"] if mount["type"] == "bind"}
    actual_binds = {target: mount for target, mount in mounts.items() if mount.get("Type") == "bind"}
    if set(reviewed_binds) != set(actual_binds) or any(
        host_path(actual_binds[target].get("Source", "")) != host_path(mount["source"])
        or actual_binds[target].get("RW") != (not mount.get("read_only", False))
        for target, mount in reviewed_binds.items() if target in actual_binds
    ):
        changed.append("media mounts or access")
    host = info.get("HostConfig", {})
    ports = {str(port["target"]) + "/tcp": [{"HostIp": port["host_ip"], "HostPort": port["published"]}] for port in service["ports"]}
    if host.get("PortBindings") != ports or host.get("PublishAllPorts"):
        changed.append("published ports")
    networks = info.get("NetworkSettings", {}).get("Networks", {})
    if set(networks) != {project + "_control"}:
        changed.append("private network")
    if host.get("Privileged") or "no-new-privileges:true" not in (host.get("SecurityOpt") or []):
        changed.append("container privileges")
    return changed


def load_receipt(deployments, identity):
    if not re.fullmatch(r"[a-f0-9]{32}", identity):
        raise DeploymentError("Choose a saved installation to check.")
    with deployments.store.db() as db:
        row = db.execute("SELECT state,payload FROM deployments WHERE id=?", (identity,)).fetchone()
    if not row or row[0] != "needs-setup":
        raise DeploymentError("Finish or resume this installation before checking its containers.")
    payload = json.loads(row[1])
    if deployments.context() != payload["context"]:
        raise DeploymentError("Select the original local Docker context before checking this installation.")
    directory = deployments.store.root / "deployments" / identity
    filename = directory / "compose.json"
    for path in (directory.parent, directory, filename):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise DeploymentError("Installation files are linked. Inspect them before continuing.")
    if not filename.is_file() or filename.read_text(encoding="utf-8") != json.dumps(payload["compose"], sort_keys=True):
        raise DeploymentError("The saved Compose file changed or is missing. No repair was attempted.")
    return payload


def inspect_container(deployments, identity, payload, key):
    return json.loads(deployments._call(["--context", payload["context"]["name"], "inspect", app_project(identity, payload) + "-" + key + "-1"], timeout=5))[0]


def check(deployments, identity):
    payload = load_receipt(deployments, identity)
    project = app_project(identity, payload)
    rows = []
    for key in payload["apps"]:
        recovery = None
        try:
            info = inspect_container(deployments, identity, payload, key)
            changed = differences(info, project, key, payload["compose"]["services"][key])
            runtime = info.get("State", {})
            health = runtime.get("Health", {}).get("Status")
            state = "changed" if changed else "paused" if runtime.get("Paused") else "restarting" if runtime.get("Restarting") else "stopped" if not runtime.get("Running") else "unhealthy" if health == "unhealthy" else "starting" if health == "starting" else "running"
            detail = "Review changed " + ", ".join(changed) + "." if changed else {
                "stopped": "Container is stopped; its reviewed settings still match.",
                "paused": "Container is paused. It cannot serve requests until resumed in Docker.",
                "restarting": "Docker is restarting this container. Check its app logs if this continues.",
                "unhealthy": "Docker reports a failed health check. Open Health for connection details.",
                "starting": "Docker is still waiting for this app to become healthy.",
                "running": "Container is running and the checked installation settings match.",
            }[state]
        except (DeploymentError, ValueError, KeyError, IndexError, TypeError):
            state, detail = "unavailable", "Could not inspect this container. It may be missing or Docker may be unavailable."
            try:
                from .app_maintenance import AppMaintenance

                maintenance = AppMaintenance(deployments)
                if maintenance.container(identity, payload, key) is None:
                    maintenance.resources(identity, payload, key)
                    state, detail = "missing", "App container is absent. Owned settings and login are retained; review Repair to bring it back."
            except (DeploymentError, ValueError, KeyError, IndexError, TypeError):
                pass
        from .app_maintenance import AppMaintenance

        recovery = AppMaintenance(deployments).pending(identity, key)
        actions = (["repair-recover"] if recovery else ["start", "repair", "remove"] if state == "stopped"
                   else ["stop", "restart", "repair", "remove"] if state in {"running", "unhealthy"}
                   else ["repair"] if state == "missing" else [])
        rows.append({"app": key, "name": CATALOG[key]["name"], "state": state, "detail": detail, "actions": actions, "recovery": recovery})
    deployments.store.audit("deployment.checked", identity)
    return {"checked_at": time.time(), "apps": rows, "notice": "Read-only check of ownership, image, mounts, ports, network and privileges. No app was restarted or repaired. This does not verify account setup, media playback or all upstream settings."}
