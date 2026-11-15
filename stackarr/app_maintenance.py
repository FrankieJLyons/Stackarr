"""Repair or remove one receipt-owned container; always retain its storage."""

import asyncio
import copy
import json
import re
import tempfile
import time
from pathlib import Path

from .app_backups import AppBackups, compatibility
from .backup_policy import direct
from .config import CATALOG
from .deployment import DeploymentError
from .deployment_check import differences, load_receipt
from .docker_names import app_project
from .integrations import collect
from .ports import available
from .store import Conflict

LABEL = "io.stackarr.maintenance"
ID = re.compile(r"^[a-f0-9]{32}$")


class AppMaintenance:
    def __init__(self, deployments):
        self.deployments, self.store = deployments, deployments.store

    def call(self, payload, *args, **kwargs):
        return self.deployments._call(["--context", payload["context"]["name"], *args], **kwargs)

    def container(self, identity, payload, key):
        name = app_project(identity, payload) + "-" + key + "-1"
        ids = self.call(payload, "ps", "-aq", "--no-trunc", "--filter", "name=^/" + name + "$").split()
        if not ids:
            return None
        if len(ids) != 1 or not re.fullmatch(r"[a-f0-9]{64}", ids[0]):
            raise DeploymentError("The app container identity is ambiguous. Nothing was replaced.")
        return json.loads(self.call(payload, "inspect", ids[0]))[0]

    def resources(self, identity, payload, key, container=None, unstarted=False):
        from .host_recovery import canonical

        canonical(payload)
        project = app_project(identity, payload)
        service = payload["compose"]["services"][key]
        for mount in service["volumes"]:
            if mount["type"] == "bind" and not direct(mount["source"]).is_dir():
                raise DeploymentError("The saved media folder is unavailable. No folder was created or app replaced.")
        image = json.loads(self.call(payload, "image", "inspect", service["image"]))[0]
        if image.get("Os") != "linux" or image.get("Architecture") != "amd64" or not re.fullmatch(r"sha256:[a-f0-9]{64}", image.get("Id", "")):
            raise DeploymentError("The saved Linux x64 image is unavailable. Keep the retained settings and restore the original image first.")
        volume = json.loads(self.call(payload, "volume", "inspect", project + "_" + key + "-config"))[0]
        labels = volume.get("Labels") or {}
        consumers = self.call(payload, "ps", "-aq", "--no-trunc", "--filter", "volume=" + project + "_" + key + "-config").split()
        if (labels.get("com.docker.compose.project") != project or labels.get("com.docker.compose.volume") != key + "-config"
                or volume.get("Driver") != "local" or volume.get("Options") or volume.get("Scope") != "local"
                or consumers != ([container["Id"]] if container else [])):
            raise DeploymentError("The configuration volume is shared or changed. No app or volume was removed.")
        network = json.loads(self.call(payload, "network", "inspect", project + "_control"))[0]
        labels = network.get("Labels") or {}
        defaults = {"com.docker.network.enable_ipv4": "true", "com.docker.network.enable_ipv6": "false"}
        if (labels.get("com.docker.compose.project") != project or labels.get("com.docker.compose.network") != "control"
                or network.get("Driver") != "bridge" or any(defaults.get(k) != v for k, v in (network.get("Options") or {}).items())):
            raise DeploymentError("The saved private app network is missing or changed. Keep the app data and inspect Docker.")
        if container:
            self.owned(identity, payload, key, container, image, unstarted=unstarted)
        auxiliary = {}
        if container:
            expected = {mount["target"] for mount in service["volumes"]}
            for mount in container["Mounts"]:
                if mount["Destination"] not in expected:
                    destination = mount["Destination"]
                    if key != "plex" or destination != "/transcode" or destination not in image.get("Config", {}).get("Volumes", {}):
                        raise DeploymentError("The app has an unreviewed extra volume. No container or data was removed.")
                    auxiliary[destination] = self.auxiliary(payload, mount.get("Name", ""), container["Id"])
        else:
            # Anonymous Plex scratch volumes have no project label. Retain only
            # the exact volume recorded before this installation removed its app.
            with self.store.db() as db:
                rows = db.execute("SELECT payload FROM deployment_actions ORDER BY created DESC").fetchall()
            for row in rows:
                saved = json.loads(row[0])
                if saved.get("deployment") == identity and saved.get("app") == key and saved.get("resources", {}).get("auxiliary"):
                    auxiliary = saved["resources"]["auxiliary"]
                    for reference in auxiliary.values():
                        if self.auxiliary(payload, reference["name"]) != reference:
                            raise DeploymentError("The retained Plex scratch volume changed. It was not adopted or removed.")
                    break
        return {"image": image["Id"], "volume": self.deployments.actions.fingerprint(volume), "network": network["Id"], "auxiliary": auxiliary}

    def auxiliary(self, payload, name, consumer=None):
        if not re.fullmatch(r"[a-f0-9]{64}", name):
            raise DeploymentError("The Plex scratch volume is not the original anonymous volume.")
        volume = json.loads(self.call(payload, "volume", "inspect", name))[0]
        consumers = self.call(payload, "ps", "-aq", "--no-trunc", "--filter", "volume=" + name).split()
        if (volume.get("Driver") != "local" or volume.get("Scope") != "local" or volume.get("Options")
                or volume.get("Labels") != {"com.docker.volume.anonymous": ""} or consumers != ([consumer] if consumer else [])):
            raise DeploymentError("The Plex scratch volume is shared or changed. No data was removed.")
        return {"name": name, "fingerprint": self.deployments.actions.fingerprint(volume)}

    def owned(self, identity, payload, key, info, image=None, unstarted=False):
        if unstarted and info["State"].get("Status") == "created" and not info["State"].get("Running"):
            # Failed binding can leave a genuinely owned, never-started container
            # unattached. Every other identity/security/mount check still applies.
            import copy

            network = app_project(identity, payload) + "_control"
            if info.get("HostConfig", {}).get("NetworkMode") == network and set(info.get("NetworkSettings", {}).get("Networks", {})) <= {network}:
                info = copy.deepcopy(info)
                info["NetworkSettings"]["Networks"] = {network: {}}
        service = payload["compose"]["services"][key]
        image = image or json.loads(self.call(payload, "image", "inspect", service["image"]))[0]
        config, host = info["Config"], info["HostConfig"]
        defaults = image.get("Config") or {}
        environment = dict(item.split("=", 1) for item in defaults.get("Env", []) if "=" in item)
        environment.update({k: str(v) for k, v in service.get("environment", {}).items()})
        actual = dict(item.split("=", 1) for item in config.get("Env", []) if "=" in item)
        labels = config.get("Labels") or {}
        if (differences(info, app_project(identity, payload), key, service) or info["Image"] != image["Id"]
                or actual != environment
                or config.get("Entrypoint") != defaults.get("Entrypoint") or config.get("Cmd") != defaults.get("Cmd")
                or config.get("User", "") != defaults.get("User", "") or host.get("CapAdd") or host.get("Devices")
                or host.get("DeviceRequests") or host.get("ExtraHosts") or host.get("Links") or host.get("AutoRemove")
                or (host.get("CapDrop") or []) != service.get("cap_drop", [])
                or host.get("SecurityOpt") != service["security_opt"]
                or host.get("RestartPolicy", {}).get("Name") != service["restart"]
                or host.get("Privileged") or host.get("ReadonlyRootfs", False) != service.get("read_only", False)
                or any(labels.get(k) != v for k, v in service.get("labels", {}).items())
                or labels.get(LABEL) and not ID.fullmatch(labels[LABEL])):
            raise DeploymentError("This container's image, environment, storage or privileges changed. Inspect it before repair or removal.")
        if info["State"].get("Paused") or info["State"].get("Restarting"):
            raise DeploymentError("The app is paused or restarting. Inspect Docker before maintenance.")

    def pending(self, identity, key):
        with self.store.db() as db:
            rows = db.execute("SELECT id,payload FROM deployment_actions WHERE state='needs-recovery' ORDER BY created DESC").fetchall()
        return next((row[0] for row in rows if (p := json.loads(row[1])).get("deployment") == identity and p.get("app") == key), None)

    def read(self, operation):
        if not operation or not ID.fullmatch(operation):
            raise DeploymentError("Choose the saved repair or removal operation.")
        with self.store.db() as db:
            row = db.execute("SELECT state,payload FROM deployment_actions WHERE id=?", (operation,)).fetchone()
        if not row or row[0] != "needs-recovery":
            raise Conflict("Check maintenance history and review the interrupted operation again.")
        review = json.loads(row[1])
        if review.get("action") not in {"repair", "remove"} or not review.get("run"):
            raise DeploymentError("This operation has no recoverable app checkpoint.")
        return review

    def review(self, identity, key, action, operation=None):
        if action not in {"repair", "remove", "repair-recover"}:
            raise DeploymentError("Choose repair or removal with settings retained.")
        if operation is not None and action != "repair-recover":
            raise DeploymentError("Choose a saved operation only for maintenance recovery.")
        payload = load_receipt(self.deployments, identity)
        if key not in payload["apps"]:
            raise DeploymentError("This app is not owned by this installation.")
        if action == "repair-recover":
            previous = self.read(operation)
            if previous["deployment"] != identity or previous["app"] != key:
                raise DeploymentError("The recovery belongs to another app.")
            if previous["receipt"] != self.deployments.actions.fingerprint(payload):
                raise DeploymentError("The installation changed after maintenance. Its data was preserved; inspect the saved checkpoint.")
            info = self.recovery_container(previous, payload)
            if previous["action"] == "repair" and previous["container"] and not info:
                self.ports(payload, key)
            if previous["run"].get("backup"):
                with tempfile.TemporaryDirectory(prefix="maintenance-review-", dir=AppBackups(self.deployments).root) as name:
                    AppBackups(self.deployments).materialize(previous["run"]["backup"], Path(name))
            return {"action": action, "deployment": identity, "app": key, "name": CATALOG[key]["name"], "operation": operation,
                    "receipt": previous["receipt"], "run": previous["run"]}
        info = self.container(identity, payload, key)
        if action == "remove" and not info:
            raise Conflict("The app container is already absent. Its retained settings can be used by Repair.")
        resources = self.resources(identity, payload, key, info)
        if action == "repair" and (not info or not info["State"].get("Running")):
            self.ports(payload, key)
        secret = self.store.secret(key)
        return {"action": action, "deployment": identity, "app": key, "name": CATALOG[key]["name"],
                "receipt": self.deployments.actions.fingerprint(payload), "resources": resources,
                "container": info["Id"] if info else None, "running": bool(info and info["State"].get("Running")),
                "runtime": self.deployments.actions.fingerprint({k: info[k] for k in ("Config", "HostConfig", "Mounts")}) if info else None,
                "connection": self.deployments.actions.fingerprint({"app": self.store.config()[1].integrations[key].model_dump(), "secret": secret})}

    @staticmethod
    def public(review):
        notice = ("Recreate only this app's container using the same saved image, ports and folders. No image is downloaded. A verified encrypted settings backup is saved first; failed repair restores that checkpoint. " if review["action"] == "repair" else
                  "Stop and remove only this app's container. Keep its settings volume, generated login, Stackarr connections, media, downloads and backups. A verified encrypted safety backup is saved first. Repair can bring the app back with the same settings. Dependent apps may report it offline. " if review["action"] == "remove" else
                  "Recover this saved maintenance operation. A failed repair restores its before-repair settings and previous running state; a completed removal stays removed with its data retained. Newer app settings may be replaced by the reviewed checkpoint. ")
        return {k: review[k] for k in ("action", "deployment", "app", "name")} | {"notice": notice + "Active work in this app is interrupted. Other containers and media files are never removed or restored."}

    @staticmethod
    def ports(payload, key):
        if any(not available(int(p["published"])) for p in payload["compose"]["services"][key]["ports"]):
            raise Conflict("This app's saved port is occupied. Free it before repair; existing services and saved settings were preserved.")

    def save(self, operation, review, phase):
        review["run"]["phase"] = phase
        with self.store.db() as db:
            db.execute("UPDATE deployment_actions SET payload=?,message=?,updated=? WHERE id=?",
                       (json.dumps(review), review["name"] + ": " + phase.replace("-", " "), time.time(), operation))

    def stop(self, review, payload, info):
        if not info:
            return
        if info["State"].get("Running"):
            self.call(payload, "stop", "--timeout", "60", info["Id"], timeout=90)
        current = self.container(review["deployment"], payload, review["app"])
        if not current or current["Id"] != info["Id"]:
            raise DeploymentError("The app changed while stopping. No replacement was attempted.")
        self.owned(review["deployment"], payload, review["app"], current)
        if current["State"].get("Running") or current["State"].get("ExitCode") == 137:
            raise DeploymentError("The app did not stop cleanly. Its container and data were retained; inspect its health before retrying.")

    def snapshot(self, review, payload, stage, kind):
        backups = AppBackups(self.deployments)
        identity = backups.snapshot({"deployment": review["deployment"], "apps": [review["app"]], "receipt": compatibility(payload)},
                                    payload | {"identity": review["deployment"]}, stage, kind)
        verify = stage / ("verify-" + identity)
        verify.mkdir()
        backups.materialize(identity, verify)
        # Never replace a missing app with empty settings and accidentally create a new account/library.
        import tarfile

        with tarfile.open(verify / review["app"] / "volume.tar") as archive:
            if not any(item.isfile() and item.size for item in archive):
                raise DeploymentError("The retained settings volume is empty. Restore a verified app backup before repair.")
        self.deployments.backup_plans.copy(identity)
        return identity

    def create(self, operation, review, payload, start=True):
        self.ports(payload, review["app"])
        self.resources(review["deployment"], payload, review["app"])
        project, key = app_project(review["deployment"], payload), review["app"]
        plan = {"services": {key: copy.deepcopy(payload["compose"]["services"][key])},
                "volumes": {key + "-config": {"external": True, "name": project + "_" + key + "-config"}},
                "networks": {"control": {"external": True, "name": project + "_control"}}}
        plan["services"][key].setdefault("labels", {})[LABEL] = operation
        for index, (destination, reference) in enumerate(review["resources"].get("auxiliary", {}).items()):
            if key != "plex" or destination != "/transcode" or self.auxiliary(payload, reference["name"]) != reference:
                raise DeploymentError("The retained scratch volume changed before repair. Settings and media were preserved.")
            alias = "retained-cache-" + str(index)
            plan["volumes"][alias] = {"external": True, "name": reference["name"]}
            plan["services"][key]["volumes"].append({"type": "volume", "source": alias, "target": destination})
        filename = direct(self.store.root / "deployments" / review["deployment"] / ("maintenance-" + operation + ".json"))
        content = json.dumps(plan, sort_keys=True)
        if filename.exists() and filename.read_text() != content:
            raise DeploymentError("The saved repair recipe changed. Existing app settings were preserved.")
        if not filename.exists():
            filename.write_text(content)
        mode = ["up", "-d", "--no-deps"] if start else ["create"]
        self.call(payload, "compose", "--project-name", project, "-f", str(filename), *mode, "--no-build", "--pull", "never", key, timeout=180)
        info = self.container(review["deployment"], payload, key)
        if not info or info["Config"].get("Labels", {}).get(LABEL) != operation:
            raise DeploymentError("The recreated app identity could not be confirmed.")
        self.resources(review["deployment"], payload, key, info)
        if bool(info["State"].get("Running")) != start:
            raise DeploymentError("Docker did not confirm the reviewed running state. Settings were retained.")
        return info

    def health(self, review, payload, seconds=120):
        key = review["app"]
        app = self.store.config()[1].integrations[key].model_copy(deep=True)
        app.url = "http://127.0.0.1:" + payload["compose"]["services"][key]["ports"][0]["published"]
        secret = self.store.secret(key)
        deadline, consecutive = time.monotonic() + seconds, 0
        while time.monotonic() < deadline:
            try:
                info = self.container(review["deployment"], payload, key)
                self.resources(review["deployment"], payload, key, info)
                if not info or not info["State"].get("Running") or info["State"].get("Health", {}).get("Status") == "unhealthy":
                    raise ValueError("App not ready")
                if secret and app.enabled:
                    asyncio.run(collect(key, app, secret))
                consecutive += 1
                if consecutive >= 2:
                    return True
            except Exception:
                consecutive = 0
            time.sleep(2)
        return False

    def protected(self, review, payload):
        if not self.store.secret(review["app"]):
            return None
        from .updates import Updates

        updates = Updates(self.deployments)
        secret = updates.credentials(review["deployment"], payload, review["app"])
        if review["app"] == "seerr":
            secret["_protected_version"] = review.get("run", {}).get("protected_version", 1)
        return self.deployments.actions.fingerprint(updates.protected(payload, review["app"], secret))

    def recovery_container(self, review, payload):
        info = self.container(review["deployment"], payload, review["app"])
        resources = self.resources(review["deployment"], payload, review["app"], info)
        if review["resources"].get("auxiliary") and resources["auxiliary"] != review["resources"]["auxiliary"]:
            raise DeploymentError("The reviewed Plex scratch volume changed. Its contents were preserved.")
        if info and info["Id"] != review["container"] and info["Config"].get("Labels", {}).get(LABEL) != review["run"]["operation"]:
            raise DeploymentError("Another container occupies the app's name or settings. It was not stopped or removed.")
        return info

    def recover(self, review, payload, stage):
        run = review["run"]
        info = self.recovery_container(review, payload)
        if review["action"] == "remove":
            if info and review["running"] and not info["State"].get("Running"):
                self.call(payload, "start", info["Id"], timeout=60)
            return "Removal completed; settings, login and media retained." if not info else "Removal did not complete; the original container and settings were retained."
        self.stop(review, payload, info)
        if run.get("backup"):
            verify = stage / "recover-snapshot"
            verify.mkdir()
            backups = AppBackups(self.deployments)
            backups.materialize(run["backup"], verify)
            # Verify ownership and consumers again immediately before configuration restore.
            self.recovery_container(review, payload)
            if not run.get("recovery_backup"):
                safety = stage / "recovery-safety"
                safety.mkdir()
                run["recovery_backup"] = backups.snapshot({"deployment": review["deployment"], "apps": [review["app"]], "receipt": compatibility(payload)},
                    payload | {"identity": review["deployment"]}, safety, "before-maintenance-recovery")
                self.save(run["operation"], review, "restoring-settings")
            backups.helper(payload | {"identity": review["deployment"]}, review["app"], verify / review["app"], restore=True)
        if info and info["Id"] != review["container"]:
            self.call(payload, "rm", info["Id"])
            info = None
        if review["container"]:
            if not info:
                info = self.create(run["operation"], review, payload, start=review["running"])
            if review["running"]:
                if not info["State"].get("Running"):
                    self.call(payload, "start", info["Id"], timeout=60)
            elif info["State"].get("Running"):
                self.stop(review, payload, info)
            if run.get("protected") and review["running"]:
                if not self.health(review, payload) or self.protected(review, payload) != run["protected"]:
                    raise DeploymentError("Previous settings were restored but app readiness could not be confirmed. Review maintenance recovery after checking Docker.")
        else:
            return "Repair did not complete; retained settings were preserved and the app remains absent. Check its saved backup, then review Repair again. Media and other apps were preserved."
        return "Repair did not complete; the previous app settings and running state were recovered. Media and other apps were preserved."

    def execute(self, review, operation):
        if not ID.fullmatch(operation):
            raise DeploymentError("Choose an approved maintenance operation.")
        if review["action"] == "repair-recover":
            previous = self.read(review["operation"])
            if self.review(review["deployment"], review["app"], "repair-recover", review["operation"]) != review:
                raise Conflict("The recovery state changed. Review it again.")
            payload = load_receipt(self.deployments, review["deployment"])
            with tempfile.TemporaryDirectory(prefix="maintenance-recovery-", dir=AppBackups(self.deployments).root) as name:
                message = self.recover(previous, payload, Path(name))
            self.save(review["operation"], previous, "recovered")
            with self.store.db() as db:
                db.execute("UPDATE deployment_actions SET state='recovered',message=?,updated=? WHERE id=?", (message, time.time(), review["operation"]))
            return message
        if self.review(review["deployment"], review["app"], review["action"]) != review:
            raise Conflict("The reviewed app, credentials or storage changed. Review again.")
        payload = load_receipt(self.deployments, review["deployment"])
        review = copy.deepcopy(review)
        review["run"] = {"operation": operation, "backup": None, "protected": None, "protected_version": 3}
        self.save(operation, review, "preparing")
        with tempfile.TemporaryDirectory(prefix="maintenance-", dir=AppBackups(self.deployments).root) as name:
            stage = Path(name)
            try:
                if review["running"]:
                    try:
                        review["run"]["protected"] = self.protected(review, payload)
                    except Exception:
                        pass  # A broken API must not prevent a configuration-preserving runtime repair.
                info = self.container(review["deployment"], payload, review["app"])
                self.stop(review, payload, info)
                self.save(operation, review, "stopped")
                review["run"]["backup"] = self.snapshot(review, payload, stage, "before-" + review["action"])
                self.save(operation, review, "backup-verified")
                self.resources(review["deployment"], payload, review["app"], self.container(review["deployment"], payload, review["app"]))
                self.save(operation, review, "removing-container")
                if info:
                    self.call(payload, "rm", info["Id"])
                if self.container(review["deployment"], payload, review["app"]):
                    raise DeploymentError("The original container was not removed. Its settings remain intact.")
                if review["action"] == "repair":
                    self.save(operation, review, "creating-container")
                    running = review["running"] or review["container"] is None
                    self.create(operation, review, payload, start=running)
                    self.save(operation, review, "checking-app")
                    if running and not self.health(review, payload):
                        raise DeploymentError("The repaired app did not pass its readiness checks.")
                    expected = review["run"]["protected"]
                    if expected and self.protected(review, payload) != expected:
                        raise DeploymentError("The repaired app's protected settings changed.")
                    if not review["running"] and review["container"]:
                        self.stop(review, payload, self.container(review["deployment"], payload, review["app"]))
                self.save(operation, review, "completed")
                return ("App repaired using its saved image, ports, settings and login. " if review["action"] == "repair" else "App container removed; settings, login and backups retained. Use Repair to bring it back. ") + "Media and other apps were preserved."
            except Exception as exc:
                review["run"]["failure_phase"] = review["run"]["phase"]
                review["run"]["failure"] = str(exc) if isinstance(exc, (DeploymentError, Conflict)) else type(exc).__name__
                try:
                    message = self.recover(review, payload, stage)
                    self.save(operation, review, "recovered")
                    return {"state": "failed-recovered", "message": message}
                except Exception:
                    self.save(operation, review, "recovery-required")
                    return {"state": "needs-recovery", "message": "App maintenance needs recovery. Check Docker and storage, then review Recover maintenance. Settings checkpoints and media were retained."}
