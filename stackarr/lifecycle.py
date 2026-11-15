"""Reviewed start/stop of exact owned containers, with no recreation or data deletion."""

import asyncio
import hashlib
import json
import re
import time
import uuid

from .config import CATALOG
from .deployment import DeploymentError
from .deployment_check import differences, inspect_container, load_receipt
from .docker_names import app_project
from .store import Conflict


class Lifecycle:
    def __init__(self, deployments):
        self.deployments, self.store = deployments, deployments.store
        from .updates import initialize

        initialize(self.store)
        with self.store.db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS deployment_actions (
                id TEXT PRIMARY KEY, state TEXT, message TEXT, created REAL, updated REAL,
                payload TEXT)""")
            db.execute("UPDATE deployment_actions SET state='interrupted',message='Interrupted. Check the app state and saved backups, then review a new action. Maintenance may have left apps stopped; a before-restore safety copy can recover their configuration.' WHERE state IN ('queued','running')")
            db.execute("UPDATE app_updates SET state='needs-recovery' WHERE state='running'")
            for identity, raw in db.execute("SELECT id,payload FROM deployment_actions WHERE state='interrupted'").fetchall():
                value = json.loads(raw)
                if value.get("action") in {"repair", "remove"} and value.get("run"):
                    phase = value["run"].get("phase")
                    state = "succeeded" if phase == "completed" else "failed-recovered" if phase == "recovered" else "needs-recovery"
                    db.execute("UPDATE deployment_actions SET state=?,message=? WHERE id=?", (state,
                        "App maintenance interrupted. Check the installation and review Recover maintenance; settings checkpoints and media were retained." if state == "needs-recovery" else "Saved app maintenance result recovered after restart.", identity))

    @staticmethod
    def fingerprint(payload):
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def review(self, identity, key, action, operation=None):
        if action in {"repair", "remove", "repair-recover"}:
            from .app_maintenance import AppMaintenance

            return AppMaintenance(self.deployments).review(identity, key, action, operation)
        if action not in ("start", "stop", "restart"):
            raise DeploymentError("Only starting and stopping an installed app are supported.")
        payload = load_receipt(self.deployments, identity)
        if key not in payload["apps"]:
            raise DeploymentError("This app was not installed by this deployment.")
        info = inspect_container(self.deployments, identity, payload, key)
        if differences(info, app_project(identity, payload), key, payload["compose"]["services"][key]):
            raise DeploymentError("This container differs from the reviewed installation. Check its settings before changing its state.")
        runtime = info["State"]
        if runtime.get("Paused") or runtime.get("Restarting"):
            raise DeploymentError("This app is paused or restarting. Inspect Docker before reviewing an action.")
        if runtime.get("Running") != (action != "start"):
            raise Conflict("The app state no longer needs this action. Check its current status.")
        container = info["Id"]
        if not re.fullmatch(r"[a-f0-9]{64}", container):
            raise DeploymentError("The exact container identity could not be verified.")
        return {"deployment": identity, "app": key, "name": CATALOG[key]["name"], "action": action,
                "container": container, "receipt": self.fingerprint(payload)}

    @staticmethod
    def public(review):
        if review["action"] in {"repair", "remove", "repair-recover"}:
            from .app_maintenance import AppMaintenance

            return AppMaintenance.public(review)
        return {key: review[key] for key in ("deployment", "app", "name", "action")} | {
            "notice": ("Stopping interrupts this app's playback, downloads or other active work. Docker allows 30 seconds to exit, then may force it to stop. Configuration volumes and media are preserved. Other apps are not stopped."
                       if review["action"] == "stop" else "Restart this app to recover from a stalled service. Active work is interrupted; Docker allows 30 seconds to exit. The same container, settings, downloads and media are preserved. Check Health afterwards." if review["action"] == "restart" else "Start the same existing container with its saved settings. No image is downloaded, container recreated or data restored. Application readiness is checked separately in Health.")}

    def enqueue(self, review):
        from .self_update import busy

        if busy(self.store.root):
            raise Conflict("Stackarr maintenance is in progress. App changes are paused.")
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM deployments WHERE state IN ('queued','running')").fetchone() or db.execute("SELECT 1 FROM deployment_actions WHERE state IN ('queued','running')").fetchone():
                raise Conflict("Another installation or app action is in progress. Wait for its result.")
            if review["action"] != "update-recover" and db.execute("SELECT 1 FROM app_updates WHERE state='needs-recovery'").fetchone():
                raise Conflict("Recover the interrupted update in Apps before another app operation.")
            if review["action"] != "repair-recover" and db.execute("SELECT 1 FROM deployment_actions WHERE state='needs-recovery'").fetchone():
                raise Conflict("Recover the interrupted app maintenance before another app operation.")
            identity, now = uuid.uuid4().hex, time.time()
            db.execute("INSERT INTO deployment_actions VALUES(?,?,?,?,?,?)", (identity, "queued", "Waiting to " + review["action"] + " " + review["name"], now, now, json.dumps(review)))
            db.execute("INSERT INTO audit(time,event,app) VALUES(?,?,?)", (now, "app." + review["action"] + "-approved", review.get("app", "")))
        return identity

    def rows(self):
        with self.store.db() as db:
            return [{"id": row[0], "state": row[1], "message": row[2], "updated": row[3]}
                    for row in db.execute("SELECT id,state,message,updated FROM deployment_actions ORDER BY created DESC LIMIT 30")]

    def busy(self):
        from .self_update import busy

        if busy(self.store.root):
            return True
        with self.store.db() as db:
            return bool(db.execute("SELECT 1 FROM deployment_actions WHERE state IN ('queued','running','needs-recovery')").fetchone()
                        or db.execute("SELECT 1 FROM app_updates WHERE state='needs-recovery'").fetchone())

    def execute(self, review):
        if review["action"] == "host-backup":
            from .host_recovery import HostBackups

            return HostBackups(self.deployments).execute(review)
        if review["action"] == "companions":
            from .companions import Companions

            return Companions(self.deployments).execute(review)
        if review["action"] == "scheduled-backup":
            from .backup_policy import BackupPlans

            return BackupPlans(self.deployments).execute(review)
        if review["action"] in {"update", "rollback", "update-recover"}:
            from .updates import Updates

            return Updates(self.deployments).execute(review)
        if review["action"] in {"backup", "restore"}:
            from .app_backups import AppBackups

            return AppBackups(self.deployments).execute(review)
        current = self.review(review["deployment"], review["app"], review["action"])
        if current != review:
            raise DeploymentError("The reviewed container or installation changed. Check it and review again.")
        # Use immutable container ID, never a name that could now refer to another app.
        payload = load_receipt(self.deployments, review["deployment"])
        command = ["--context", payload["context"]["name"], review["action"]]
        if review["action"] in {"stop", "restart"}:
            command += ["--timeout", "30"]
        self.deployments._call([*command, review["container"]], timeout=60)
        info = inspect_container(self.deployments, review["deployment"], payload, review["app"])
        if info["Id"] != review["container"] or info["State"].get("Running") != (review["action"] != "stop"):
            raise DeploymentError("Docker did not confirm the expected app state. Check the installation before taking another action.")

    async def run_one(self):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id,payload FROM deployment_actions WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
            if not row:
                return False
            identity, raw = row
            db.execute("UPDATE deployment_actions SET state='running',updated=? WHERE id=?", (time.time(), identity))
        review = json.loads(raw)
        try:
            if review["action"] in {"repair", "remove", "repair-recover"}:
                from .app_maintenance import AppMaintenance

                result = await asyncio.to_thread(AppMaintenance(self.deployments).execute, review, identity)
            else:
                result = await asyncio.to_thread(self.execute, review)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            state = "failed"
            message = str(exc) if isinstance(exc, (DeploymentError, Conflict)) else "App action could not be confirmed. Check installation status before reviewing another action."
        else:
            state = result["state"] if isinstance(result, dict) else "succeeded"
            message = result["message"] if isinstance(result, dict) else result or review["name"] + (" stopped. Its volumes and media are preserved." if review["action"] == "stop" else " restarted. Check Health for application readiness." if review["action"] == "restart" else " started. Check Health for application readiness.")
        with self.store.db() as db:
            db.execute("UPDATE deployment_actions SET state=?,message=?,updated=? WHERE id=?", (state, message, time.time(), identity))
            db.execute("INSERT INTO audit(time,event,app) VALUES(?,?,?)", (time.time(), "app." + review["action"] + "-" + state, review.get("app", "")))
        return True
