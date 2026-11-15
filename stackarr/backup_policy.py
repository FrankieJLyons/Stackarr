"""Host-approved scheduled configuration backups and verified second-disk copies."""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from pydantic import Field, StrictBool, StrictInt

from .app_backups import AppBackups, digest
from .config import CATALOG, Model
from .deployment import DeploymentError
from .deployment_check import load_receipt
from .store import Conflict


class BackupPolicyIntent(Model):
    enabled: StrictBool = False
    time: str = Field(default="03:00", pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    keep: StrictInt = Field(default=7, ge=1, le=90)
    deployments: list[str] = Field(default_factory=list, max_length=9)
    destination: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


def direct(path):
    path = Path(path)
    if not path.is_absolute() or path == path.parent:
        raise DeploymentError("Choose a dedicated backup folder, not a drive root.")
    for item in (path, *path.parents):
        if item.is_symlink() or item.is_junction():
            raise DeploymentError("Backup storage must not use filesystem links.")
    return path


def disk(path):
    """Physical disk identity on the supported Windows host; fail closed elsewhere."""
    path = direct(path)
    if os.name != "nt" or not re.fullmatch(r"[a-zA-Z]:\\", path.anchor):
        raise DeploymentError("Second-disk verification requires a local Windows drive.")
    env = os.environ.copy()
    env["STACKARR_BACKUP_DRIVE"] = path.anchor[0]
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
        "$ErrorActionPreference='Stop'; (Get-Partition -DriveLetter $env:STACKARR_BACKUP_DRIVE).DiskNumber"],
        env=env, capture_output=True, text=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode or not re.fullmatch(r"\d+", result.stdout.strip()):
        raise DeploymentError("Could not verify the backup drive. Connect it and try again.")
    return result.stdout.strip()


def next_run(clock, at):
    now = datetime.fromtimestamp(clock)
    hour, minute = map(int, at.split(":"))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    # Naive local datetime.timestamp honours the host's DST rules for that date.
    return target.timestamp()


class BackupPlans:
    def __init__(self, deployments):
        self.deployments, self.store = deployments, deployments.store
        AppBackups(deployments)
        with self.store.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS app_backup_policy (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER, value BLOB)")
            db.execute("CREATE TABLE IF NOT EXISTS app_backup_destinations (id TEXT PRIMARY KEY, value BLOB)")
            db.execute("CREATE TABLE IF NOT EXISTS app_backup_copies (backup TEXT PRIMARY KEY, destination TEXT, verified REAL)")
            if not db.execute("SELECT 1 FROM app_backup_policy").fetchone():
                self.write(db, 1, {**BackupPolicyIntent().model_dump(), "namespace": uuid.uuid4().hex,
                                  "next_run": None, "last_status": "Not scheduled", "last_success": None})

    def write(self, db, revision, value):
        db.execute("INSERT OR REPLACE INTO app_backup_policy VALUES(1,?,?)",
                   (revision, self.store.cipher.encrypt(json.dumps(value).encode())))

    def read(self):
        with self.store.db() as db:
            revision, raw = db.execute("SELECT revision,value FROM app_backup_policy WHERE id=1").fetchone()
        return revision, json.loads(self.store.cipher.decrypt(raw))

    def destinations(self):
        with self.store.db() as db:
            rows = db.execute("SELECT id,value FROM app_backup_destinations").fetchall()
        return [{"id": identity, **json.loads(self.store.cipher.decrypt(raw))} for identity, raw in rows]

    def admit(self, path):
        path = direct(path)
        if not path.is_dir() or path.resolve().is_relative_to(self.store.root.resolve()):
            raise DeploymentError("Choose an existing dedicated folder outside Stackarr's data directory.")
        if disk(path) == disk(self.store.root):
            raise DeploymentError("Choose a folder on a different physical disk from Stackarr.")
        # Never allow backup retention to overlap media, the checkout or controller data.
        for row in self.deployments.rows():
            try:
                payload = load_receipt(self.deployments, row["id"])
            except (ValueError, OSError):
                continue
            for service in payload["compose"]["services"].values():
                for mount in service.get("volumes", []):
                    if isinstance(mount, dict) and mount.get("type") == "bind":
                        media = Path(mount["source"]).resolve()
                        if path.resolve().is_relative_to(media) or media.is_relative_to(path.resolve()):
                            raise DeploymentError("Choose a backup folder separate from media and downloads.")
        existing = next((row for row in self.destinations() if Path(row["path"]) == path), None)
        identity = existing["id"] if existing else uuid.uuid4().hex
        value = {"path": str(path), "name": str(path), "disk": disk(path)}
        with self.store.db() as db:
            db.execute("INSERT OR REPLACE INTO app_backup_destinations VALUES(?,?)",
                       (identity, self.store.cipher.encrypt(json.dumps(value).encode())))
        return {"id": identity, "name": str(path)}

    def choose(self):
        if os.name != "nt":
            raise DeploymentError("Choose a backup folder on the Windows host.")
        script = """Add-Type -AssemblyName System.Windows.Forms
$chooser=New-Object System.Windows.Forms.FolderBrowserDialog
$chooser.Description='Choose a dedicated backup folder on another physical disk. Media is not backed up.'
$chooser.ShowNewFolderButton=$true
try { if ($chooser.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Write($chooser.SelectedPath) } } finally { $chooser.Dispose() }
"""
        result = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-Command", script],
            capture_output=True, text=True, timeout=180, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode or not result.stdout.strip():
            raise DeploymentError("No backup folder was selected. Your settings stayed unchanged.")
        return self.admit(result.stdout.strip())

    def destination(self, policy, create=False):
        row = next((row for row in self.destinations() if row["id"] == policy["destination"]), None)
        if not row:
            raise DeploymentError("Choose a host-approved backup folder first.")
        root = direct(row["path"])
        if not root.is_dir() or disk(root) != row["disk"] or disk(root) == disk(self.store.root):
            raise DeploymentError("The separate backup disk is unavailable or changed. No old backups were removed.")
        target = direct(root / ("stackarr-" + policy["namespace"]))
        marker = target / "owner.json"
        expected = {"format": 1, "namespace": policy["namespace"]}
        if not target.exists() and create:
            target.mkdir()
            marker.write_text(json.dumps(expected), encoding="utf-8")
        if (not target.is_dir() or marker.is_symlink() or marker.is_junction()
                or not marker.is_file() or json.loads(marker.read_text()) != expected):
            raise DeploymentError("Backup folder ownership could not be verified. Existing files were preserved.")
        return target

    def listing(self):
        revision, policy = self.read()
        return {"revision": revision, "policy": {k: v for k, v in policy.items() if k != "namespace"},
                "destinations": [{"id": row["id"], "name": row["name"]} for row in self.destinations()],
                "timezone": time.tzname[time.localtime().tm_isdst],
                "notice": "Backups run while Docker and the Stackarr controller are running. Missed nights run once after startup. Media files are excluded. Keep the recovery key separately."}

    def review(self, value):
        intent = BackupPolicyIntent.model_validate(value)
        if len(set(intent.deployments)) != len(intent.deployments):
            raise DeploymentError("Select each installation once.")
        if intent.enabled and not intent.deployments:
            raise DeploymentError("Select at least one owned installation.")
        names = []
        for identity in intent.deployments:
            payload = load_receipt(self.deployments, identity)
            names.extend(CATALOG[key]["name"] for key in payload["apps"])
        revision, policy = self.read()
        if intent.destination:
            candidate = policy | {"destination": intent.destination}
            self.destination(candidate, create=True)
        return {"action": "backup-policy", "name": "Backup schedule", "revision": revision,
                "policy": intent.model_dump(), "apps": names,
                "notice": (f"Back up the selected apps nightly at {intent.time} in the host's local time. "
                    f"Keep the newest {intent.keep} scheduled copies per installation; manual, safety and update recovery snapshots are preserved. "
                    if intent.enabled else "Disable automatic app backups. Existing backups are retained. ")
                    + ("Verify an encrypted copy on the selected separate disk before removing older scheduled copies. " if intent.destination else "Keep snapshots on this computer only. ")
                    + "Running selected apps stop briefly and restart; media and downloads are never restored or deleted."}

    def configure(self, review):
        current = self.review(review["policy"])
        if current != review:
            raise Conflict("Backup settings changed. Review them again.")
        revision, old = self.read()
        policy = old | review["policy"]
        policy["next_run"] = next_run(time.time(), policy["time"]) if policy["enabled"] else None
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT revision FROM app_backup_policy WHERE id=1").fetchone()[0] != revision:
                raise Conflict("Backup settings changed. Review them again.")
            self.write(db, revision + 1, policy)
        self.store.audit("app-backup.schedule-saved")
        return {"saved": True}

    def run_now(self):
        revision, policy = self.read()
        if not policy["deployments"]:
            raise DeploymentError("Save a backup plan with selected apps first.")
        return {"id": self.deployments.actions.enqueue({"action": "scheduled-backup", "name": "Docker app backups", "revision": revision})}

    def tick(self, now=None):
        now = time.time() if now is None else now
        revision, policy = self.read()
        if not policy["enabled"] or not policy["next_run"] or policy["next_run"] > now:
            return False
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            fresh, raw = db.execute("SELECT revision,value FROM app_backup_policy WHERE id=1").fetchone()
            current = json.loads(self.store.cipher.decrypt(raw))
            if fresh != revision or current["next_run"] != policy["next_run"]:
                return False
            if (db.execute("SELECT 1 FROM deployments WHERE state IN ('queued','running')").fetchone()
                    or db.execute("SELECT 1 FROM deployment_actions WHERE state IN ('queued','running','needs-recovery')").fetchone()
                    or db.execute("SELECT 1 FROM app_updates WHERE state='needs-recovery'").fetchone()):
                return False
            identity = uuid.uuid4().hex
            review = {"action": "scheduled-backup", "name": "Docker app backups", "revision": revision}
            db.execute("INSERT INTO deployment_actions VALUES(?,?,?,?,?,?)",
                       (identity, "queued", "Scheduled app backup queued", now, now, json.dumps(review)))
            policy["next_run"] = next_run(now, policy["time"])
            policy["last_status"] = "Queued"
            self.write(db, revision, policy)
        return True

    def reconcile_startup(self):
        revision, policy = self.read()
        if policy["last_status"] not in {"Queued", "Running"}:
            return
        with self.store.db() as db:
            if db.execute("SELECT 1 FROM deployment_actions WHERE state IN ('queued','running')").fetchone():
                return
            if policy["last_status"] == "Queued":
                policy["next_run"] = time.time() if policy["enabled"] else None
                policy["last_status"] = "A queued backup was missed during restart; the schedule will retry once."
            else:
                policy["enabled"], policy["next_run"] = False, None
                policy["last_status"] = "Backup interrupted. Check app state in Apps, then review and enable the plan again. Existing snapshots and media were preserved."
            self.write(db, revision + 1, policy)

    def copy(self, identity):
        _, policy = self.read()
        if not policy["destination"]:
            return
        root = self.destination(policy, create=True)
        service = AppBackups(self.deployments)
        manifest = service.manifest(identity)
        source = direct(service.root / identity)
        with tempfile.TemporaryDirectory(prefix="verify-", dir=service.root) as stage:
            service.materialize(identity, Path(stage))
        final = direct(root / identity)
        if final.exists():
            self.external(identity, policy["destination"])  # Authenticate an existing copy too.
            self.record_copy(identity, policy["destination"])
            return
        stage = direct(root / ("partial-" + uuid.uuid4().hex))
        stage.mkdir()
        try:
            hashes = {}
            for name in [*(key + ".enc" for key in manifest["apps"]), "controller.enc"]:
                item = source / name
                if item.is_symlink() or item.is_junction():
                    raise DeploymentError("Backup files must not be links.")
                shutil.copyfile(item, stage / name)
                hashes[name] = digest(item)
                if digest(stage / name) != hashes[name]:
                    raise DeploymentError("Separate-disk copy verification failed. Local backups were retained.")
            with self.store.db() as db:
                created = db.execute("SELECT created FROM app_backups WHERE id=?", (identity,)).fetchone()[0]
            envelope = {"id": identity, "created": created, "manifest": manifest, "files": hashes}
            with (stage / "snapshot.enc").open("xb") as out:
                out.write(self.store.cipher.encrypt(json.dumps(envelope).encode()))
                out.flush()
                os.fsync(out.fileno())
            os.replace(stage, final)
            self.external(identity, policy["destination"])
            self.record_copy(identity, policy["destination"])
        finally:
            if stage.exists():
                self.remove_files(stage, [*(key + ".enc" for key in manifest["apps"]), "controller.enc", "snapshot.enc"])

    def record_copy(self, identity, destination):
        with self.store.db() as db:
            db.execute("INSERT OR REPLACE INTO app_backup_copies VALUES(?,?,?)", (identity, destination, time.time()))

    def external(self, identity, destination=None):
        if not re.fullmatch(r"[a-f0-9]{32}", identity):
            raise DeploymentError("Choose a saved backup.")
        _, policy = self.read()
        if destination is None:
            with self.store.db() as db:
                row = db.execute("SELECT destination FROM app_backup_copies WHERE backup=?", (identity,)).fetchone()
            destination = row[0] if row else policy["destination"]
        policy = policy | {"destination": destination}
        directory = direct(self.destination(policy) / identity)
        metadata = directory / "snapshot.enc"
        if metadata.is_symlink() or metadata.is_junction() or metadata.stat().st_size > 1024 * 1024:
            raise DeploymentError("The separate-disk backup metadata is invalid.")
        value = json.loads(self.store.cipher.decrypt(metadata.read_bytes()))
        manifest = value["manifest"]
        expected = {*(key + ".enc" for key in manifest["apps"]), "controller.enc"}
        if value["id"] != identity or set(value["files"]) != expected or set(manifest["apps"]) - set(CATALOG):
            raise DeploymentError("The separate-disk backup identity is invalid.")
        for name, checksum in value["files"].items():
            item = directory / name
            if item.is_symlink() or item.is_junction() or digest(item) != checksum:
                raise DeploymentError("Separate-disk backup verification failed. No restore was started.")
        return directory, value

    @staticmethod
    def remove_files(directory, names):
        directory = direct(directory)
        # Deliberately no recursive delete: remove only exact owned payload filenames.
        if set(item.name for item in directory.iterdir()) - set(names):
            raise DeploymentError("Unexpected files in a backup folder. No files were removed.")
        for name in names:
            item = directory / name
            if item.is_symlink() or item.is_junction():
                raise DeploymentError("Backup retention cannot follow links.")
        for name in names:
            (directory / name).unlink(missing_ok=True)
        directory.rmdir()

    def retain(self, deployment):
        _, policy = self.read()
        service = AppBackups(self.deployments)
        with self.store.db() as db:
            rows = db.execute("SELECT id FROM app_backups WHERE deployment=? ORDER BY created DESC", (deployment,)).fetchall()
            updates = db.execute("SELECT value FROM app_updates").fetchall()
        protected = set()
        for row in updates:
            value = json.loads(self.store.cipher.decrypt(row[0]))
            protected.update(v for k, v in value.items() if "backup" in k and isinstance(v, str))
        scheduled = [row[0] for row in rows if service.manifest(row[0])["kind"] == "scheduled"]
        if scheduled:
            with tempfile.TemporaryDirectory(prefix="retention-check-", dir=service.root) as stage:
                service.materialize(scheduled[0], Path(stage))
        if policy["destination"]:
            for identity in scheduled[:policy["keep"]]:
                self.external(identity)
        for identity in scheduled[policy["keep"]:]:
            if identity in protected:
                continue
            manifest = service.manifest(identity)
            names = [*(key + ".enc" for key in manifest["apps"]), "controller.enc"]
            if policy["destination"]:
                directory, _ = self.external(identity)
                self.remove_files(directory, [*names, "snapshot.enc"])
            local = service.root / identity
            if local.exists():
                self.remove_files(local, names)
            with self.store.db() as db:
                db.execute("DELETE FROM app_backups WHERE id=?", (identity,))
                db.execute("DELETE FROM app_backup_copies WHERE backup=?", (identity,))

    def execute(self, review):
        revision, policy = self.read()
        if revision != review["revision"]:
            raise Conflict("The backup plan changed. Run the saved plan again.")
        with self.store.db() as db:
            self.write(db, revision, policy | {"last_status": "Running"})
        try:
            if policy["destination"]:
                self.destination(policy, create=True)  # Missing drive fails before any app downtime.
            for identity in policy["deployments"]:
                service = AppBackups(self.deployments)
                service.execute(service.review(identity), kind="scheduled")
                self.retain(identity)
        except Exception:
            self.result(revision, False)
            raise
        self.result(revision, True)
        return "Scheduled app backups verified; retention applied to scheduled copies only. Media and downloads stayed untouched."

    def result(self, revision, success):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            current, raw = db.execute("SELECT revision,value FROM app_backup_policy WHERE id=1").fetchone()
            if current != revision:
                return
            policy = json.loads(self.store.cipher.decrypt(raw))
            policy["last_status"] = "Verified" if success else "Backup failed; existing backups retained. Check Docker and the backup disk."
            if success:
                policy["last_success"] = time.time()
            elif policy["enabled"]:
                policy["next_run"] = time.time() + 3600
            self.write(db, revision, policy)
