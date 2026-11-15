"""Consistent encrypted backups of receipt-verified configuration volumes only.

No archive uploads, browser paths, media mounts, image updates or container recreation.
Restores retain a separate pre-restore snapshot and roll back failed extraction.
"""

import copy
import hashlib
import json
import posixpath
import re
import sqlite3
import struct
import tarfile
import tempfile
import time
import uuid
from contextlib import closing
from pathlib import Path, PurePosixPath

from .config import CATALOG
from .deployment import DeploymentError
from .deployment_check import differences, inspect_container, load_receipt
from .docker_names import app_project

CHUNK = 4 * 1024 * 1024
MAX_ARCHIVE = 20 * 1024**3


def compatibility(payload):
    payload = copy.deepcopy(payload)
    for service in payload["compose"]["services"].values():
        labels = service.get("labels", {})
        labels.pop("io.stackarr.update", None)
        if not labels:
            service.pop("labels", None)
    from .lifecycle import Lifecycle

    return Lifecycle.fingerprint(payload)


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def validate_tar(path):
    """Validate without extracting on Windows or trusting tar's path handling."""
    count, total, names, links = 0, 0, {}, {}
    with tarfile.open(path, "r:") as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            count += 1
            total += member.size
            if (name.is_absolute() or ".." in name.parts or "\\" in member.name
                    or ":" in member.name or not (member.isfile() or member.isdir() or member.issym() or member.islnk())
                    or str(name) in names or count > 200000 or total > MAX_ARCHIVE):
                raise DeploymentError("Backup contains unsupported files or exceeds the restore limit. No data was restored.")
            names[str(name)] = member
            if member.issym() or member.islnk():
                target = member.linkname
                if not target or target.startswith("/") or "\\" in target or ":" in target:
                    raise DeploymentError("Backup contains an unsafe configuration link.")
                target = posixpath.normpath(str(name.parent / target) if member.issym() else target)
                if target == ".." or target.startswith("../"):
                    raise DeploymentError("Backup link escapes the configuration volume.")
                links[str(name)] = target
        # No archive member can write through a link, including links defined later in the tar.
        # Link chains are rejected; hard links can refer only to an archived regular file.
        for name in names:
            if any(str(parent) in links for parent in PurePosixPath(name).parents):
                raise DeploymentError("Backup contains files beneath a configuration link.")
        for name, target in links.items():
            if target in links or any(str(parent) in links for parent in PurePosixPath(target).parents):
                raise DeploymentError("Backup contains an unsupported link chain.")
            if names[name].islnk() and (target not in names or not names[target].isfile()):
                raise DeploymentError("Backup hard link does not reference an archived file.")


class AppBackups:
    def __init__(self, deployments):
        self.deployments, self.store = deployments, deployments.store
        self.root = self.store.root / "app-backups"
        for path in (self.store.root, self.root):
            if path.is_symlink() or path.is_junction():
                raise DeploymentError("Backup storage must not be a filesystem link.")
        self.root.mkdir(mode=0o700, exist_ok=True)
        if "," in str(self.root.resolve()):
            raise DeploymentError("Choose a Stackarr data directory without commas before using Docker backups.")
        with self.store.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS app_backups (id TEXT PRIMARY KEY, deployment TEXT, created REAL, manifest BLOB)")

    def manifest(self, identity):
        if not re.fullmatch(r"[a-f0-9]{32}", identity):
            raise DeploymentError("Choose a saved Docker backup.")
        with self.store.db() as db:
            row = db.execute("SELECT manifest FROM app_backups WHERE id=?", (identity,)).fetchone()
        if not row:
            raise DeploymentError("This Docker backup is unavailable.")
        return json.loads(self.store.cipher.decrypt(row[0]))

    def rows(self):
        with self.store.db() as db:
            rows = db.execute("SELECT id,deployment,created FROM app_backups ORDER BY created DESC LIMIT 100").fetchall()
            copies = {row[0] for row in db.execute("SELECT backup FROM app_backup_copies")} if db.execute("SELECT 1 FROM sqlite_master WHERE name='app_backup_copies'").fetchone() else set()
        return [{"id": row[0], "deployment": row[1], "created": row[2], "off_disk": row[0] in copies,
                 "local_available": (self.root / row[0]).is_dir(),
                 "apps": self.manifest(row[0])["apps"],
                 "kind": self.manifest(row[0])["kind"]} for row in rows]

    def review(self, identity, backup=None, apps=None):
        payload = load_receipt(self.deployments, identity)
        if backup:
            manifest = self.manifest(backup)
            if manifest["deployment"] != identity or manifest["receipt"] != compatibility(payload):
                raise DeploymentError("This backup belongs to a different installation or app version. Use Updates to roll back an image and its matching data.")
            apps = manifest["apps"]
        apps = payload["apps"] if apps is None else apps
        if not apps or set(apps) - set(payload["apps"]) or len(apps) != len(set(apps)):
            raise DeploymentError("Choose owned apps in this installation.")
        containers = {}
        for key in apps:
            try:
                info = inspect_container(self.deployments, identity, payload, key)
            except DeploymentError:
                from .app_maintenance import AppMaintenance

                maintenance = AppMaintenance(self.deployments)
                if maintenance.container(identity, payload, key) is not None:
                    raise
                maintenance.resources(identity, payload, key)
                if backup:
                    raise DeploymentError("Repair the missing app container before restoring its settings. Retained settings can still be backed up.") from None
                containers[key] = {"id": None, "running": False}
                continue
            runtime = info["State"]
            if (differences(info, app_project(identity, payload), key, payload["compose"]["services"][key])
                    or runtime.get("Paused") or runtime.get("Restarting")
                    or not re.fullmatch(r"[a-f0-9]{64}", info.get("Id", ""))):
                raise DeploymentError("An app changed or is restarting. Check this installation before maintenance.")
            containers[key] = {"id": info["Id"], "running": bool(runtime.get("Running"))}
            # The volume must exist, belong to this exact Compose project, and have no other consumers.
            volume = app_project(identity, payload) + "_" + key + "-config"
            record = json.loads(self.deployments._call(["--context", payload["context"]["name"], "volume", "inspect", volume]))[0]
            labels = record.get("Labels") or {}
            consumers = self.deployments._call(["--context", payload["context"]["name"], "ps", "-aq", "--no-trunc", "--filter", "volume=" + volume]).split()
            if (labels.get("com.docker.compose.project") != app_project(identity, payload)
                    or labels.get("com.docker.compose.volume") != key + "-config"
                    or consumers != [info["Id"]]):
                raise DeploymentError("A configuration volume is shared or its ownership changed. Maintenance was blocked.")
        receipt = compatibility(payload)
        return {"deployment": identity, "apps": apps, "name": "Docker app configuration",
                "action": "restore" if backup else "backup", "backup": backup,
                "receipt": receipt, "containers": containers}

    @staticmethod
    def public(review):
        return {key: review[key] for key in ("deployment", "action", "backup")} | {
            "apps": [CATALOG[key]["name"] for key in review["apps"]],
            "notice": ("Restore app databases, credentials and settings to this snapshot. Newer app configuration will be replaced. A separate safety backup is created first; failed extraction rolls back from it. " if review["action"] == "restore" else "Save encrypted app databases, credentials and settings. ")
            + "Selected running apps stop briefly and restart afterwards; stopped apps stay stopped. Media and download folders are never mounted by the backup helper or restored. Stackarr dashboard settings remain unchanged. When a separate backup disk is configured, a verified encrypted copy is saved there. Keep the recovery key separately; media files need their own backup."}

    def crypt(self, source, destination, decrypt=False):
        # Chunk index binds ordering; authenticated terminal binds truncation, including whole chunks.
        with source.open("rb") as inp, destination.open("xb") as out:
            index, total = 0, 0
            while True:
                if decrypt:
                    length = inp.read(4)
                    if len(length) != 4:
                        raise DeploymentError("Backup is truncated. No restore was started.")
                    size = struct.unpack("!I", length)[0]
                    if not 0 < size <= CHUNK * 2:
                        raise DeploymentError("Invalid encrypted backup.")
                    block = self.store.cipher.decrypt(inp.read(size))
                    if block[:8] != struct.pack("!Q", index):
                        raise DeploymentError("Backup chunk order changed.")
                    block = block[8:]
                    if not block:
                        if inp.read(1):
                            raise DeploymentError("Backup has unexpected trailing data.")
                        break
                    out.write(block)
                else:
                    block = inp.read(CHUNK)
                    token = self.store.cipher.encrypt(struct.pack("!Q", index) + block)
                    out.write(struct.pack("!I", len(token)))
                    out.write(token)
                    if not block:
                        break
                total += len(block)
                if total > MAX_ARCHIVE:
                    raise DeploymentError("App configuration exceeds the 20 GiB backup limit.")
                index += 1

    def helper(self, payload, key, directory, restore=False):
        context = payload["context"]["name"]
        volume = app_project(payload["identity"], payload) + "_" + key + "-config"
        # All arguments and shell text are fixed. Only this receipt-owned named volume is writable.
        script = ("find /volume -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + && tar -xpf /backup/volume.tar -C /volume"
                  if restore else "tar -cpf /backup/volume.tar -C /volume .")
        name = "stackarr-backup-helper-" + uuid.uuid4().hex
        args = ["--context", context, "run", "--name", name, "--rm", "--pull=never",
                "--network", "none", "--read-only", "--cap-drop", "ALL",
                "--cap-add", "CHOWN", "--cap-add", "DAC_OVERRIDE", "--cap-add", "FOWNER",
                "--security-opt", "no-new-privileges:true", "--user", "0:0", "--entrypoint", "/bin/sh",
                "--mount", "type=volume,src=" + volume + ",dst=/volume" + ("" if restore else ",readonly"),
                "--mount", "type=bind,src=" + str(directory.resolve()) + ",dst=/backup" + (",readonly" if restore else ""),
                payload["compose"]["services"][key]["image"], "-c", script]
        try:
            self.deployments._call(args, timeout=600)
        finally:
            # A timed-out CLI may leave the helper running. Confirm it is gone before restarting apps.
            self.deployments._call(["--context", context, "rm", "-f", name], timeout=30) if self.deployments._call(
                ["--context", context, "ps", "-aq", "--filter", "name=^/" + name + "$"]).strip() else None

    def snapshot(self, review, payload, stage, kind="manual"):
        identity = uuid.uuid4().hex
        directory = self.root / identity
        directory.mkdir(mode=0o700)
        manifest = {"deployment": review["deployment"], "receipt": review["receipt"],
                    "apps": review["apps"], "kind": kind, "hashes": {}, "installation": payload}
        for key in review["apps"]:
            work = stage / ("save-" + key)
            work.mkdir()
            self.helper(payload, key, work)
            archive = work / "volume.tar"
            validate_tar(archive)
            manifest["hashes"][key] = digest(archive)
            self.crypt(archive, directory / (key + ".enc"))
        # Preserve host receipts and encrypted credential checkpoints for manual disaster recovery.
        # Normal app restore deliberately leaves the active controller/dashboard databases intact.
        checkpoint = stage / ("controller-" + identity + ".db")
        with self.store.db() as source, closing(sqlite3.connect(checkpoint)) as target:
            source.backup(target)
        self.crypt(checkpoint, directory / "controller.enc")
        # Commit only complete snapshots. Partial folders never appear as restorable backups.
        with self.store.db() as db:
            db.execute("INSERT INTO app_backups VALUES(?,?,?,?)", (identity, review["deployment"], time.time(),
                       self.store.cipher.encrypt(json.dumps(manifest).encode())))
        return identity

    def materialize(self, identity, stage):
        manifest = self.manifest(identity)
        directory = self.root / identity
        if not all((directory / (key + ".enc")).is_file() for key in manifest["apps"]):
            from .backup_policy import BackupPlans

            directory, envelope = BackupPlans(self.deployments).external(identity)
            if envelope["manifest"] != manifest:
                raise DeploymentError("Separate-disk snapshot differs from the saved receipt. No restore was started.")
        if directory.is_symlink() or directory.is_junction():
            raise DeploymentError("Backup directories must not be filesystem links.")
        for key in manifest["apps"]:
            source = directory / (key + ".enc")
            if source.is_symlink() or source.is_junction():
                raise DeploymentError("Backup files must not be filesystem links.")
            work = stage / key
            work.mkdir()
            self.crypt(source, work / "volume.tar", decrypt=True)
            if digest(work / "volume.tar") != manifest["hashes"][key]:
                raise DeploymentError("Backup checksum failed. No restore was started.")
            validate_tar(work / "volume.tar")

    def execute(self, review, kind="manual"):
        current = self.review(review["deployment"], review["backup"], review["apps"])
        if current != review:
            raise DeploymentError("The installation changed. Review maintenance again.")
        payload = load_receipt(self.deployments, review["deployment"]) | {"identity": review["deployment"]}
        context = payload["context"]["name"]
        with tempfile.TemporaryDirectory(prefix="work-", dir=self.root) as temporary:
            stage = Path(temporary)
            if review["backup"]:
                restore = stage / "restore"
                restore.mkdir()
                self.materialize(review["backup"], restore)  # Verify everything before downtime/writes.
            restart, safety = [], None
            try:
                for key, container in review["containers"].items():
                    if container["id"] is None:
                        continue  # An absent app has no writer; its verified retained volume is backed up in place.
                    if container["running"]:
                        restart.append(container["id"])
                        self.deployments._call(["--context", context, "stop", "--timeout", "60", container["id"]], timeout=90)
                    info = inspect_container(self.deployments, review["deployment"], payload, key)
                    if (info["Id"] != container["id"] or info["State"].get("Running")
                            or differences(info, app_project(review["deployment"], payload), key, payload["compose"]["services"][key])
                            or info["State"].get("ExitCode") == 137):
                        raise DeploymentError("An app did not exit cleanly. Backup/restore was cancelled; check its status.")
                self.review(review["deployment"], review["backup"], review["apps"])
                safety = self.snapshot(review, payload, stage, "before-restore" if review["backup"] else kind)
                if not review["backup"]:
                    verified = stage / "verify-saved"
                    verified.mkdir()
                    self.materialize(safety, verified)
                if review["backup"]:
                    rollback = stage / "rollback"
                    rollback.mkdir()
                    self.materialize(safety, rollback)
                    try:
                        for key in review["apps"]:
                            self.helper(payload, key, restore / key, restore=True)
                    except Exception:
                        try:
                            for key in review["apps"]:
                                self.helper(payload, key, rollback / key, restore=True)
                        except Exception:
                            restart.clear()  # Never start apps on partially restored databases.
                            raise DeploymentError("Restore and automatic rollback need attention. Apps remain stopped. Review the saved before-restore backup to recover; media is untouched.") from None
                        raise DeploymentError("Restore failed; the before-restore configuration was recovered. Media is untouched.") from None
            finally:
                failures = []
                for container in restart:
                    try:
                        self.deployments._call(["--context", context, "start", container], timeout=60)
                    except Exception:
                        failures.append(container)
                if failures:
                    raise DeploymentError("Configuration was preserved, but some apps could not restart. Check the installation and use Start when Docker is ready.")
        from .backup_policy import BackupPlans

        try:
            BackupPlans(self.deployments).copy(safety)
        except Exception:
            raise DeploymentError("App configuration was saved locally and apps restarted, but the separate-disk copy failed. Existing backups were retained; reconnect the backup disk and run the plan again.") from None
        return ("Docker app configuration restored; safety backup retained. " if review["backup"] else "Encrypted Docker app backup saved. ") + "Media and downloads were untouched. Check Health for application readiness."
