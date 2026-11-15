"""Repair only the saved Stackarr runtime, using checked configuration copies."""

import copy
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from .app_backups import digest
from .deployment import DeploymentError
from .ports import available
from .runtime_storage import RESERVE, check
from .self_removal import SelfRemoval, archive_files
from .self_update import fingerprint, pending
from .store import Conflict


class SelfRepair:
    def __init__(self, updates):
        self.updates, self.root = updates, updates.root
        self.retained = SelfRemoval(updates)

    def idle(self):
        with closing(sqlite3.connect(self.root / "controller/state/stackarr.db")) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            checks = {"deployment_actions": "state IN ('queued','running','needs-recovery')",
                      "app_updates": "state IN ('running','needs-recovery')",
                      "deployments": "state NOT IN ('needs-setup','superseded')"}
            if any(table in tables and db.execute("SELECT 1 FROM " + table + " WHERE " + condition).fetchone()
                   for table, condition in checks.items()):
                raise Conflict("Finish or recover app operations before repairing Stackarr.")

    def inspect(self, runtime):
        u = self.updates
        self.retained.context(runtime)
        info = self.retained.container(runtime)
        resources = self.retained.resources(runtime, info)
        if not info or not info["State"].get("Running"):
            if not available(runtime["port"]):
                raise Conflict("Stackarr's saved dashboard port is occupied. Free it before repair; the other service was not stopped.")
        if u.listening(runtime["controller_port"]):
            probe = u.controller_identity or u.controller_probe(runtime)
            if probe.get("executable") != u.release(runtime["release"])[1]["files"]["StackarrPreview.exe"] or probe.get("checking"):
                raise DeploymentError("The private controller does not match the saved release. It was not stopped.")
        elif not available(runtime["controller_port"]):
            raise Conflict("Stackarr's saved private port is occupied. The other service was preserved.")
        self.idle()
        check(u.home)
        check(self.root / "controller/state")
        with tempfile.TemporaryDirectory(prefix="repair-review-", dir=u.home) as name:
            stage = Path(name)
            u.helper(runtime, runtime["volume"], stage)
            required = RESERVE + (stage / "dashboard-volume.tar").stat().st_size * 5 + (self.root / "controller/state/stackarr.db").stat().st_size * 5
            check(u.home, required)
            check(self.root / "controller/state", required)
            before = {"dashboard": fingerprint(stage), "dashboard_key": digest(stage / "secrets.key"),
                      "controller": fingerprint(self.root / "controller/state"), "controller_key": digest(self.root / "controller/state/secrets.key"),
                      "inventory": fingerprint(self.root / "controller/state", True), "dashboard_inventory": fingerprint(stage, True),
                      "container": info["Id"] if info else None}
            files = archive_files(stage / "dashboard-volume.tar")
        return before, resources, files

    def review(self):
        u = self.updates
        if pending(self.root):
            raise Conflict("Recover the current Stackarr maintenance first.")
        if (self.root / "stackarr-removed.json").exists():
            raise Conflict("Stackarr was intentionally removed. Review reinstall from Start Stackarr.")
        if not (self.root / "stackarr-runtime.json").is_file() and not u.controller_identity:
            raise DeploymentError("This installation has no verified saved Stackarr release. Use its original setup or whole-host recovery; no data was adopted.")
        runtime = u.active()
        self.retained.context(runtime)
        # Preparing a verified local image cache never stops or replaces apps.
        u.load_image(runtime["release"])
        before, resources, files = self.inspect(runtime)
        supervisor, manifest = u.stage_directory(u.package_root)
        if manifest.get("runtime_repair") != 1:
            raise DeploymentError("Open a repair-capable Stackarr package to review runtime repair.")
        return {"action": "repair", "source": runtime, "target": copy.deepcopy(runtime), "before": before,
                "snapshot": None, "resources": resources, "preserved_files": files, "supervisor": supervisor,
                "notice": "Recreate only Stackarr's dashboard and restart its private controller using the same verified release and checked copies of your settings. Your password, connections, app logins and backups are preserved. A verified encrypted checkpoint is saved first. Failed checks recover the original settings. Media apps keep running; no app container, volume or media folder is repaired or restored."}

    def preflight(self, job):
        if self.updates.active() != job["source"]:
            raise Conflict("Stackarr's active release changed. Review repair again.")
        before, resources, files = self.inspect(job["source"])
        if before != job["before"] or resources != job["resources"] or files != job["preserved_files"]:
            raise Conflict("Stackarr's runtime or retained settings changed. Repair was cancelled before downtime; review it again.")

    def recover(self, job):
        u = self.updates
        source, target = job["source"], job["target"]
        current = self.retained.container(source)
        original = current
        if current:
            mounts = {row["Destination"]: row for row in current["Mounts"]}
            if mounts.get("/var/lib/stackarr", {}).get("Name") != source["volume"]:
                self.retained.resources(target, current)
                original = None
        if self.retained.resources(source, original) != job["resources"]:
            raise DeploymentError("Original Stackarr storage or enrollment changed. Recovery preserved it for inspection.")
        # The original volume is never a candidate write target. Refuse a
        # changed backup/configuration file before bringing it back online.
        with tempfile.TemporaryDirectory(prefix="repair-recovery-", dir=u.home) as name:
            stage = Path(name)
            u.helper(source, source["volume"], stage)
            if archive_files(stage / "dashboard-volume.tar") != job["preserved_files"]:
                raise DeploymentError("Original Stackarr configuration files changed. Recovery did not overwrite them.")
        u.recover(job, repair_checked=True)
