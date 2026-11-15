"""Read disk capacity only for receipt-verified owned media mounts."""

import shutil
from pathlib import Path

from .deployment import DeploymentError
from .deployment_check import differences, inspect_container, load_receipt
from .docker_names import app_project


def owned_storage(deployments):
    with deployments.store.db() as db:
        identities = [row[0] for row in db.execute(
            "SELECT id FROM deployments WHERE state='needs-setup' ORDER BY created DESC LIMIT 20")]
    drives = {}
    for identity in identities:
        try:
            payload = load_receipt(deployments, identity)
            for key in payload["apps"]:
                service = payload["compose"]["services"][key]
                mounts = [v for v in service.get("volumes", []) if isinstance(v, dict)
                          and v.get("type") == "bind" and v.get("target") == "/data"]
                if not mounts:
                    continue
                info = inspect_container(deployments, identity, payload, key)
                if differences(info, app_project(identity, payload), key, service):
                    continue
                path = Path(mounts[0]["source"])
                if not path.is_absolute() or not path.is_dir():
                    continue
                volume = path.resolve().anchor
                if volume not in drives:
                    usage = shutil.disk_usage(path)
                    drives[volume] = {"free_gb": round(usage.free / 1024**3, 1),
                                      "total_gb": round(usage.total / 1024**3, 1)}
        except (DeploymentError, OSError, ValueError, KeyError, TypeError, IndexError):
            continue
    rows = list(drives.values())
    return ({"available": True, "drives": rows, **rows[0]} if rows else
            {"available": False, "message": "No verified media mount is available. Connect the installation computer or check your media folder."})
