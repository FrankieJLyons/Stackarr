"""Portable, authenticated host checkpoints; recovery only into empty owned resources.

Media is never archived, extracted or deleted. Original app ports and identities
are retained so saved app-to-app connections continue to work after a host loss.
"""

import base64
import copy
import json
import os
import re
import shutil
import sqlite3
import tarfile
import tempfile
import time
import uuid
from contextlib import closing, contextmanager
from pathlib import Path
from types import SimpleNamespace

from cryptography.fernet import Fernet

from .app_backups import AppBackups, digest, validate_tar
from .backup_policy import direct
from .config import CATALOG, Config
from .deployment import DeploymentError, Deployments
from .deployment_check import differences, inspect_container, load_receipt
from .docker_names import app_project, available_project
from .installer import compose_plan
from .store import Conflict, Store

ID = re.compile(r"^[a-f0-9]{32}$")
LABEL = "io.stackarr.recovery"
NOTICE = ("Save all owned app settings, databases, protected logins, the Stackarr account and installation receipts. "
          "Running apps stop briefly for their snapshots and restart afterwards. Media and downloads are excluded. "
          "Keep the recovery file and your recovery key separately. Recovery requires an empty installation, "
          "the original app ports, and access to your separately preserved media.")


def checkpoint(store, target):
    with store.db() as source, closing(sqlite3.connect(target)) as destination:
        source.backup(destination)


def clean_database(path):
    with closing(sqlite3.connect(path)) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise DeploymentError("The recovered database is damaged. Nothing was started.")
        for table in ("sessions", "setup_handoffs", "controller_requests"):
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                db.execute('DELETE FROM "' + table + '"')
        db.commit()


def canonical(payload):
    """Rebuild our fixed Compose recipe, refusing arbitrary archived Docker options."""
    config = Config.model_validate(payload["config"])
    if "project" in payload:
        app_project("", payload)
    apps = payload["apps"]
    if not apps or len(set(apps)) != len(apps) or set(apps) - set(CATALOG):
        raise DeploymentError("The recovery app list is unsupported.")
    expected = compose_plan(config)["compose"]
    expected["networks"] = {"control": {}}
    if set(expected["services"]) != set(apps):
        raise DeploymentError("The recovery installation is inconsistent.")
    for key, service in expected["services"].items():
        saved = payload["compose"]["services"][key]
        repository = CATALOG[key]["image"].rsplit(":", 1)[0]
        if not re.fullmatch(re.escape(repository) + r"@sha256:[a-f0-9]{64}", saved["image"]):
            raise DeploymentError("Recovery requires the original pinned application images.")
        service.update(image=saved["image"], platform="linux/amd64",
                       logging={"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}})
        labels = saved.get("labels", {})
        if set(labels) - {"io.stackarr.update", LABEL, "io.stackarr.install-ports"} or any(not ID.fullmatch(v) for v in labels.values()):
            raise DeploymentError("The recovery installation has unsupported labels.")
        if labels:
            service["labels"] = labels
    if expected != payload["compose"]:
        raise DeploymentError("The recovery Compose recipe changed. Nothing was created.")
    return expected


class HostBackups:
    def __init__(self, deployments, dashboard_port=None):
        self.deployments, self.store = deployments, deployments.store
        self.port = dashboard_port or int(os.environ.get("STACKARR_PORT", "28000"))
        self.root = direct(self.store.root / "host-recovery")
        self.root.mkdir(exist_ok=True, mode=0o700)

    def dashboard(self):
        shared = str((self.store.root.parent / "shared").resolve())
        names = self.deployments._call(["ps", "-aq", "--no-trunc", "--filter", "publish=" + str(self.port)]).split()
        matches = []
        for name in names:
            info = json.loads(self.deployments._call(["inspect", name]))[0]
            labels = info["Config"].get("Labels") or {}
            mounts = {m["Destination"]: m for m in info["Mounts"]}
            enrollment = mounts.get("/run/stackarr-controller", {})
            state = mounts.get("/var/lib/stackarr", {})
            bindings = info["HostConfig"].get("PortBindings", {}).get("8787/tcp")
            source = enrollment.get("Source", "")
            # Docker Desktop can return its Linux host-mount spelling for a Windows bind.
            match = re.fullmatch(r"/(?:run/desktop/mnt/host|host_mnt)/([a-zA-Z])/(.*)", source)
            if os.name == "nt" and match:
                source = match[1] + ":/" + match[2]
            if (labels.get("com.docker.compose.service") == "stackarr"
                    and os.path.normcase(os.path.normpath(source)) == os.path.normcase(os.path.normpath(shared))
                    and enrollment.get("RW") is False and state.get("Type") == "volume"
                    and bindings == [{"HostIp": "127.0.0.1", "HostPort": str(self.port)}]
                    and info["State"].get("Running")):
                matches.append(info["Id"])
        if len(matches) != 1:
            raise DeploymentError("Open this installation's packaged dashboard before preparing host recovery.")
        # Verify the enrolled files themselves, without returning their contents.
        script = ("import hashlib,pathlib; p=pathlib.Path('/run/stackarr-controller'); "
                  "print(hashlib.sha256((p/'rpc.key').read_bytes()+(p/'controller.crt').read_bytes()).hexdigest())")
        import hashlib

        actual = self.deployments._call(["exec", matches[0], "python", "-c", script]).strip()
        expected = hashlib.sha256((Path(shared) / "rpc.key").read_bytes() + (Path(shared) / "controller.crt").read_bytes()).hexdigest()
        if actual != expected:
            raise DeploymentError("The dashboard enrollment changed. No host backup was started.")
        return matches[0]

    def review(self):
        # The dashboard's recent-operation list is deliberately bounded; a host
        # checkpoint must include older owned installations as well.
        with self.store.db() as db:
            rows = db.execute("SELECT id,state FROM deployments ORDER BY created DESC").fetchall()
        if any(state not in {"needs-setup", "superseded"} for _, state in rows):
            raise Conflict("Finish or resolve installations before preparing host recovery.")
        service = AppBackups(self.deployments)
        reviews = [service.review(identity) for identity, state in rows if state == "needs-setup"]
        if not reviews:
            raise DeploymentError("Install an app before preparing host recovery.")
        apps = [key for row in reviews for key in row["apps"]]
        if len(apps) != len(set(apps)):
            raise DeploymentError("Multiple owned installations contain the same app. Resolve their identities before host backup.")
        for row in reviews:
            canonical(load_receipt(self.deployments, row["deployment"]))
        return {"action": "host-backup", "name": "Whole-host recovery backup", "reviews": reviews,
                "dashboard": self.dashboard(), "dashboard_revision": self.dashboard_revision()}

    def dashboard_revision(self):
        return int(self.deployments._call(["exec", self.dashboard(), "python", "-c",
            "import sqlite3; print(sqlite3.connect('/var/lib/stackarr/stackarr.db').execute('SELECT revision FROM settings WHERE id=1').fetchone()[0])"]).strip())

    @staticmethod
    def public(review):
        return {"action": "host-backup", "name": review["name"], "notice": NOTICE,
                "apps": [CATALOG[k]["name"] for r in review["reviews"] for k in r["apps"]]}

    def execute(self, review):
        if self.review() != review:
            raise Conflict("The installation changed. Review the host backup again.")
        service, selected = AppBackups(self.deployments), []
        for row in review["reviews"]:
            service.execute(row, kind="host-recovery")
            selected.append(next(r["id"] for r in service.rows() if r["deployment"] == row["deployment"]))
        return self.pack(selected, review["reviews"], expected_revision=review["dashboard_revision"])

    def pack(self, selected, reviews, expected_revision=None, scheduled=False):
        """Package complete verified snapshots and fresh SQLite checkpoints."""
        service = AppBackups(self.deployments)
        _, policy = self.deployments.backup_plans.read()
        identity = uuid.uuid4().hex
        final = self.root / (identity + ".stackarr-recovery")
        with tempfile.TemporaryDirectory(prefix="build-", dir=self.root) as temporary:
            stage = Path(temporary)
            # SQLite's backup API is consistent while monitoring continues. Never copy a live WAL database.
            script = ("import base64,json,pathlib,sqlite3,tempfile; "
                      "p=pathlib.Path(tempfile.mktemp(dir='/tmp')); "
                      "s=sqlite3.connect('/var/lib/stackarr/stackarr.db'); d=sqlite3.connect(p); s.backup(d); d.close(); s.close(); "
                      "print(json.dumps({'db':base64.b64encode(p.read_bytes()).decode(),"
                      "'key':pathlib.Path('/var/lib/stackarr/secrets.key').read_text()})); p.unlink()")
            raw = self.deployments._call(["exec", self.dashboard(), "python", "-c", script])
            if len(raw) > 32 * 1024**2:
                raise DeploymentError("Dashboard recovery checkpoint exceeds the supported limit.")
            dashboard = json.loads(raw)
            (stage / "dashboard.db").write_bytes(base64.b64decode(dashboard["db"], validate=True))
            Fernet(dashboard["key"].encode())
            (stage / "dashboard.key").write_text(dashboard["key"], encoding="ascii")
            clean_database(stage / "dashboard.db")
            with closing(sqlite3.connect(stage / "dashboard.db")) as db:
                revision = db.execute("SELECT revision FROM settings WHERE id=1").fetchone()[0]
            if expected_revision is not None and revision != expected_revision:
                raise Conflict("Dashboard settings changed during backup. Prepare host recovery again.")
            checkpoint(self.store, stage / "controller.db")
            clean_database(stage / "controller.db")
            metadata = {"format": 1, "id": identity, "namespace": policy["namespace"], "created": time.time(),
                        "scheduled": scheduled, "snapshots": [], "hashes": {}}
            for backup, review in zip(selected, reviews, strict=True):
                manifest = service.manifest(backup)
                canonical(manifest["installation"])
                verify = stage / ("verify-" + backup)
                verify.mkdir()
                service.materialize(backup, verify)
                source = service.root / backup
                if not source.is_dir():
                    source, _ = self.deployments.backup_plans.external(backup)
                for key in manifest["apps"]:
                    shutil.copyfile(direct(source / (key + ".enc")), stage / (backup + "-" + key + ".enc"))
                metadata["snapshots"].append({"backup": backup, "manifest": manifest,
                    "running": {k: c["running"] for k, c in review["containers"].items()}})
            metadata["hashes"] = {p.name: digest(p) for p in stage.iterdir() if p.is_file()}
            (stage / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
            archive = stage / "host.tar"
            with tarfile.open(archive, "w") as tar:
                for name in [*metadata["hashes"], "metadata.json"]:
                    tar.add(stage / name, arcname=name, recursive=False)
            partial = final.with_suffix(".partial")
            service.crypt(archive, partial)
            service.crypt(partial, stage / "verified.tar", decrypt=True)
            if digest(archive) != digest(stage / "verified.tar"):
                raise DeploymentError("Host recovery backup verification failed.")
            partial.rename(final)
        external = None
        if policy["destination"]:
            destination = self.deployments.backup_plans.destination(policy, create=True)
            external = direct(destination / final.name)
            partial = direct(external.with_suffix(".partial"))
            with final.open("rb") as source, partial.open("xb") as target:
                shutil.copyfileobj(source, target)
            if digest(partial) != digest(final):
                raise DeploymentError("The separate-disk host recovery copy failed verification.")
            partial.rename(external)
        self.store.audit("host-backup.verified", identity)
        return "Whole-host recovery backup verified: " + str(external or final) + ". Keep your recovery key separately. Media is excluded."


class Recovery:
    def __init__(self, bundle, keyfile, package):
        self.bundle, self.keyfile, self.package = direct(bundle), direct(keyfile), direct(package)
        key = json.loads(self.keyfile.read_text(encoding="utf-8-sig"))
        if key.get("format") != 1 or not ID.fullmatch(key.get("namespace", "")):
            raise DeploymentError("Choose a Stackarr backup recovery key.")
        self.key, self.namespace = key["key"].encode(), key["namespace"]
        self.crypt = SimpleNamespace(store=SimpleNamespace(cipher=Fernet(self.key)))
        self.manifest = json.loads((self.package / "manifest.json").read_text(encoding="utf-8-sig"))
        if self.manifest["schema"] != 1 or not re.fullmatch(r"sha256:[a-f0-9]{64}", self.manifest["image_id"]):
            raise DeploymentError("Choose a complete compatible Stackarr package.")
        for name in ("StackarrPreview.exe", "stackarr-image.tar", "Start-StackarrPreview.ps1"):
            if digest(direct(self.package / name)) != self.manifest["files"][name]:
                raise DeploymentError("The Stackarr package failed verification.")

    @contextmanager
    def opened(self):
        with tempfile.TemporaryDirectory(prefix="stackarr-recovery-") as temporary:
            stage = Path(temporary)
            try:
                AppBackups.crypt(self.crypt, self.bundle, stage / "host.tar", decrypt=True)
                validate_tar(stage / "host.tar")
                with tarfile.open(stage / "host.tar") as tar:
                    members = tar.getmembers()
                    if any(not m.isfile() or Path(m.name).name != m.name for m in members):
                        raise DeploymentError("The host recovery file has unsupported contents.")
                    meta = json.loads(tar.extractfile("metadata.json").read(1024**2))
                    if meta["format"] != 1 or meta["namespace"] != self.namespace or not ID.fullmatch(meta["id"]):
                        raise DeploymentError("The recovery key belongs to a different installation.")
                    expected = {"controller.db", "dashboard.db", "dashboard.key"}
                    apps, identities = set(), set()
                    for row in meta["snapshots"]:
                        m = row["manifest"]
                        if (not ID.fullmatch(row["backup"]) or not ID.fullmatch(m["deployment"])
                                or m["deployment"] in identities or set(m["apps"]) != set(m["installation"]["apps"])
                                or set(m["apps"]) != set(row["running"]) or apps & set(m["apps"])
                                or any(type(v) is not bool for v in row["running"].values())):
                            raise DeploymentError("The recovery snapshot inventory is inconsistent.")
                        canonical(m["installation"])
                        identities.add(m["deployment"])
                        apps.update(m["apps"])
                        expected.update(row["backup"] + "-" + key + ".enc" for key in m["apps"])
                    if not apps or set(meta["hashes"]) != expected or {m.name for m in members} != expected | {"metadata.json"}:
                        raise DeploymentError("The host recovery file is incomplete.")
                    for name in expected:
                        with (stage / name).open("xb") as output, tar.extractfile(name) as source:
                            shutil.copyfileobj(source, output)
                        if digest(stage / name) != meta["hashes"][name]:
                            raise DeploymentError("Host recovery checksum failed.")
                for row in meta["snapshots"]:
                    for key in row["manifest"]["apps"]:
                        target = stage / row["manifest"]["deployment"] / key
                        target.mkdir(parents=True)
                        AppBackups.crypt(self.crypt, stage / (row["backup"] + "-" + key + ".enc"), target / "volume.tar", decrypt=True)
                        if digest(target / "volume.tar") != row["manifest"]["hashes"][key]:
                            raise DeploymentError("An app recovery checksum failed.")
                        validate_tar(target / "volume.tar")
                Fernet((stage / "dashboard.key").read_bytes())
                clean_database(stage / "controller.db")
                clean_database(stage / "dashboard.db")
                yield stage, meta
            except (DeploymentError, Conflict):
                raise
            except Exception:
                raise DeploymentError("The recovery file or key could not be verified. No existing apps were changed.") from None

    @staticmethod
    def roots(meta):
        return sorted({row["manifest"]["installation"]["config"]["storage"]["data_root"]
                       for row in meta["snapshots"] if any(k in {"plex", "sonarr", "radarr", "qbittorrent"} for k in row["manifest"]["apps"])})

    def review(self, destination, media, port=28000, controller_port=28010):
        destination = direct(destination)
        if "," in str(destination) or "," in tempfile.gettempdir():
            raise DeploymentError("Choose a recovery state directory and temporary directory without commas.")
        if any(type(p) is not int or not 1 <= p <= 65535 for p in (port, controller_port)):
            raise DeploymentError("Choose valid recovery dashboard and controller ports.")
        if destination.exists() and any(destination.iterdir()):
            raise DeploymentError("Choose an empty recovery directory. Existing state is preserved.")
        with self.opened() as (stage, meta):
            if set(media) != set(self.roots(meta)):
                raise DeploymentError("Choose an existing media folder for each saved media location.")
            for path in media.values():
                if not direct(path).is_dir():
                    raise DeploymentError("Reconnect your preserved media folder before recovery.")
                if destination.resolve().is_relative_to(Path(path).resolve()) or Path(path).resolve().is_relative_to(destination.resolve()):
                    raise DeploymentError("Keep recovery state separate from media.")
            deployment = SimpleNamespace(_call=Deployments._call, runner=__import__("subprocess").run)
            deployment._call = Deployments._call.__get__(deployment)
            deployment.context = Deployments.context.__get__(deployment)
            context = deployment.context()
            ports = [int(row["manifest"]["installation"]["compose"]["services"][k]["ports"][0]["published"])
                     for row in meta["snapshots"] for k in row["manifest"]["apps"]]
            from .ports import available

            if len(ports) != len(set(ports)) or any(not available(p) for p in ports):
                raise DeploymentError("An original app port is busy. Recovery preserves saved connections; free that port first. Existing services were left running.")
            reserved = set(ports)
            chosen = []
            for preferred in (port, controller_port):
                candidates = [*range(preferred, min(preferred + 256, 65536)), *range(49152, 49408)]
                candidate = next((p for p in candidates if 1 <= p <= 65535 and p not in reserved and available(p)), None)
                if candidate is None:
                    raise DeploymentError("No available Stackarr port was found.")
                chosen.append(candidate)
                reserved.add(candidate)
            self.absent(deployment, context, meta)
            return {"format": 1, "bundle": str(self.bundle), "keyfile": str(self.keyfile), "package": str(self.package),
                    "sha256": digest(self.bundle), "destination": str(destination), "media": media,
                    "port": chosen[0], "controller_port": chosen[1], "context": context,
                    "id": uuid.uuid4().hex, "backup": meta["id"], "apps": sorted(k for r in meta["snapshots"] for k in r["manifest"]["apps"]),
                    "notice": "Recreate these apps at their original ports in empty Docker volumes. Keep the saved Stackarr password and app logins. Media folders are attached, never restored or deleted. Backup schedules stay paused until reviewed."}

    @staticmethod
    def absent(deployment, context, meta):
        base = ["--context", context["name"]]
        for row in meta["snapshots"]:
            identity = row["manifest"]["deployment"]
            project = app_project(identity, row["manifest"]["installation"])
            for args in (["ps", "-aq", "--filter", "label=com.docker.compose.project=" + project],
                         ["volume", "ls", "-q", "--filter", "label=com.docker.compose.project=" + project],
                         ["network", "ls", "-q", "--filter", "name=^" + project + "_control$"]):
                if deployment._call([*base, *args]).strip():
                    raise DeploymentError("Apps, networks or volumes from this installation still exist. Recovery will not overwrite or adopt them.")
            names = set(deployment._call([*base, "volume", "ls", "-q"]).split())
            if any(project + "_" + k + "-config" in names for k in row["manifest"]["apps"]):
                raise DeploymentError("An original configuration volume still exists. Recovery will not replace it.")

    def execute(self, review):
        if not ID.fullmatch(review.get("id", "")):
            raise DeploymentError("Choose a saved recovery review.")
        if digest(self.bundle) != review["sha256"]:
            raise DeploymentError("The recovery file changed. Review it again.")
        target = direct(review["destination"])
        journal_path = target / "recovery.json"
        retry = journal_path.is_file()
        if not retry:
            current = self.review(target, review["media"], review["port"], review["controller_port"])
            if any(current[k] != review[k] for k in ("sha256", "context", "port", "controller_port", "apps", "backup")):
                raise Conflict("Recovery conditions changed. Review recovery again.")
        else:
            journal = json.loads(direct(journal_path).read_text())
            if journal["review"] != review or journal["phase"] not in {"volumes-created", "failed"}:
                raise Conflict("This recovery directory cannot be resumed automatically.")
        target.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.opened() as (stage, meta):
            self._restore(review, target, stage, meta, retry)
        return {"passed": True, "destination": str(target), "url": "http://localhost:" + str(review["port"]),
                "apps": review["apps"], "media_restored": False, "schedules_paused": True}

    def _restore(self, review, target, stage, meta, retry):
        journal_path = target / "recovery.json"
        journal = json.loads(journal_path.read_text()) if retry else {"review": review, "phase": "preparing", "containers": {}}
        def save(phase):
            journal["phase"] = phase
            temporary = journal_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(journal), encoding="utf-8")
            os.replace(temporary, journal_path)
        save(journal["phase"])
        controller_root = direct(target / "controller")
        state = direct(controller_root / "state")
        for name in ("stackarr.db", "secrets.key"):
            direct(state / name)
        if not retry:
            state.mkdir(parents=True, mode=0o700)
            shutil.copyfile(stage / "controller.db", state / "stackarr.db")
            (state / "secrets.key").write_bytes(self.key)
            dashboard_state = target / "recovered-dashboard"
            dashboard_state.mkdir(mode=0o700)
            shutil.copyfile(stage / "dashboard.db", dashboard_state / "stackarr.db")
            shutil.copyfile(stage / "dashboard.key", dashboard_state / "secrets.key")
            for root in (state, dashboard_state):
                store = Store(root)
                revision, config = store.config()
                data = config.model_dump()
                if data["storage"]["data_root"] in review["media"]:
                    data["storage"]["data_root"] = review["media"][data["storage"]["data_root"]]
                store.save(Config.model_validate(data), revision)
                with store.db() as db:
                    for table in ("deployment_actions", "app_updates", "app_backups", "app_backup_copies", "app_backup_destinations", "controller_media_roots"):
                        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                            db.execute('DELETE FROM "' + table + '"')
                    if root == state:
                        db.execute("DELETE FROM deployments")
                    if db.execute("SELECT 1 FROM sqlite_master WHERE name='setup_draft'").fetchone():
                        db.execute("DELETE FROM setup_draft")
            host = Deployments(Store(state))
            revision, policy = host.backup_plans.read()
            with host.store.db() as db:
                host.backup_plans.write(db, revision + 1, policy | {"enabled": False, "next_run": None, "destination": None,
                    "last_status": "Recovered host. Review backup storage and enable the schedule again."})
            project = available_project(host._call, "controller")
            installation = {"owner": "stackarr-docker-preview-v1", "project": project, "port": review["port"],
                            "controller_port": review["controller_port"], "media_root": next(iter(review["media"].values()), "")}
            (target / "installation.json").write_text(json.dumps(installation), encoding="utf-8")
            from .controller_enrollment import enroll

            enroll(controller_root)
            from .media_folders import grant

            for path in review["media"].values():
                grant(host.store, path)
            for row in meta["snapshots"]:
                identity = row["manifest"]["deployment"]
                payload = copy.deepcopy(row["manifest"]["installation"])
                payload["context"] = review["context"]
                old = payload["config"]["storage"]["data_root"]
                if old in review["media"]:
                    payload["config"]["storage"]["data_root"] = review["media"][old]
                    for service in payload["compose"]["services"].values():
                        for mount in service["volumes"]:
                            if mount["type"] == "bind":
                                mount["source"] = review["media"][old]
                for service in payload["compose"]["services"].values():
                    service.setdefault("labels", {})[LABEL] = review["id"]
                canonical(payload)
                directory = state / "deployments" / identity
                directory.mkdir(parents=True)
                (directory / "compose.json").write_text(json.dumps(payload["compose"], sort_keys=True), encoding="utf-8")
                with host.store.db() as db:
                    db.execute("INSERT INTO deployments VALUES(?,?,?,?,?,?)", (identity, "needs-setup", "Recovered host configuration", time.time(), time.time(), json.dumps(payload)))
        else:
            host = Deployments(Store(state))
        if host.context() != review["context"]:
            raise DeploymentError("Docker context changed. Select the reviewed local context.")
        from .ports import available

        for path in review["media"].values():
            if not direct(path).is_dir():
                raise DeploymentError("Reconnect the reviewed media folder before resuming.")
        payloads = [(r, load_receipt(host, r["manifest"]["deployment"])) for r in meta["snapshots"]]
        try:
            if retry and journal.get("dashboard_ready"):
                installation = json.loads((target / "installation.json").read_text())
                volume = installation["project"] + "_dashboard-state"
                record = json.loads(host._call(["volume", "inspect", volume]))[0]
                if (record.get("Labels", {}).get(LABEL) != review["id"]
                        or host._call(["ps", "-aq", "--filter", "volume=" + volume]).strip()):
                    raise DeploymentError("The new dashboard volume changed or is in use. Recovery was not replayed.")
            if not retry:
                self.absent(host, review["context"], meta)  # Repeat immediately before creating anything in Docker.
                for row, payload in payloads:
                    identity = row["manifest"]["deployment"]
                    base = ["--context", review["context"]["name"], "compose", "--project-name", app_project(identity, payload),
                            "-f", str(state / "deployments" / identity / "compose.json")]
                    from .bundled_images import verify

                    for service in payload["compose"]["services"].values():
                        verify(lambda args: host._call(["--context", review["context"]["name"], *args]), service["image"])
                    host._call([*base, "pull", "--policy", "missing"], timeout=600)
                    for key in payload["apps"]:
                        if not available(int(payload["compose"]["services"][key]["ports"][0]["published"])):
                            raise DeploymentError("An app port became busy. Existing services are preserved.")
                    host._call([*base, "create"], timeout=180)
                    for key in payload["apps"]:
                        info = inspect_container(host, identity, payload, key)
                        if differences(info, app_project(identity, payload), key, payload["compose"]["services"][key]):
                            raise DeploymentError("A new recovery container failed ownership checks.")
                        journal["containers"][identity + ":" + key] = info["Id"]
                    save("creating-volumes")
                save("volumes-created")
            for row, payload in payloads:
                identity = row["manifest"]["deployment"]
                for key in payload["apps"]:
                    info = inspect_container(host, identity, payload, key)
                    if (info["Id"] != journal["containers"].get(identity + ":" + key)
                            or differences(info, app_project(identity, payload), key, payload["compose"]["services"][key])
                            or info["Config"]["Labels"].get(LABEL) != review["id"]):
                        raise DeploymentError("A recovery container changed. It was not adopted.")
                    if info["State"].get("Running"):
                        host._call(["--context", review["context"]["name"], "stop", "--timeout", "60", info["Id"]], timeout=90)
                AppBackups(host).review(identity)  # Includes unshared, correctly labelled named-volume checks.
            for row, payload in payloads:
                identity = row["manifest"]["deployment"]
                for key in payload["apps"]:
                    AppBackups(host).helper(payload | {"identity": identity}, key, stage / identity / key, restore=True)
            installation = json.loads((target / "installation.json").read_text())
            volume = installation["project"] + "_dashboard-state"
            image = self.manifest["image_id"]
            host._call(["load", "--input", str(self.package / "stackarr-image.tar")], timeout=180)
            if not journal.get("dashboard_ready"):
                if volume not in host._call(["volume", "ls", "-q"]).split():
                    host._call(["volume", "create", "--label", "com.docker.compose.project=" + installation["project"],
                                "--label", "com.docker.compose.volume=dashboard-state", "--label", LABEL + "=" + review["id"], volume])
                record = json.loads(host._call(["volume", "inspect", volume]))[0]
                if (record.get("Labels", {}).get(LABEL) != review["id"]
                        or host._call(["ps", "-aq", "--filter", "volume=" + volume]).strip()):
                    raise DeploymentError("The new dashboard volume changed or is in use.")
                script = ("import os,pathlib,shutil; p=pathlib.Path('/volume'); "
                          "assert {n.name for n in p.iterdir()} <= {'stackarr.db','secrets.key'}; "
                          "[shutil.copyfile('/backup/'+n,p/n) for n in ('stackarr.db','secrets.key')]; "
                          "[os.chown(p/n,10001,10001) for n in ('stackarr.db','secrets.key')]; os.chown(p,10001,10001)")
                host._call(["run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL", "--cap-add", "CHOWN",
                            "--security-opt", "no-new-privileges:true", "--user", "0:0", "--entrypoint", "python",
                            "--mount", "type=volume,src=" + volume + ",dst=/volume",
                            "--mount", "type=bind,src=" + str(target / "recovered-dashboard") + ",dst=/backup,readonly", image, "-c", script], timeout=120)
                journal["dashboard_ready"] = True
                save("volumes-created")
                # The only remaining plaintext checkpoints live in their normal protected state stores.
                directory = target / "recovered-dashboard"
                for name in ("stackarr.db", "secrets.key"):
                    direct(directory / name).unlink()
                directory.rmdir()
            for row, payload in payloads:
                identity = row["manifest"]["deployment"]
                for key in payload["apps"]:
                    if row["running"][key]:
                        host._call(["--context", review["context"]["name"], "start", journal["containers"][identity + ":" + key]], timeout=90)
            save("complete")
            host.store.audit("host-recovery.completed", review["backup"])
        except Exception as exc:
            journal["failure_phase"] = journal["phase"]
            journal["failure"] = str(exc) if isinstance(exc, (DeploymentError, Conflict)) else type(exc).__name__
            # Stop only our exact, still-owned new containers. Keep volumes and the checkpoint for retry/inspection.
            for row, payload in payloads:
                identity = row["manifest"]["deployment"]
                for key in payload["apps"]:
                    try:
                        info = inspect_container(host, identity, payload, key)
                        if info["Id"] == journal["containers"].get(identity + ":" + key) and info["Config"]["Labels"].get(LABEL) == review["id"]:
                            host._call(["--context", review["context"]["name"], "stop", "--timeout", "60", info["Id"]], timeout=90)
                    except Exception:
                        pass
            save("failed")
            raise DeploymentError("Recovery did not complete. Only new recovery containers were stopped; their volumes and the recovery file are retained. Reopen the saved recovery review to retry. Existing apps and media were not restored or deleted.") from None
