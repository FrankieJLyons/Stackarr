"""Reviewed Stackarr release swaps. App containers and media are never targets.

An external copy of the known working controller supervises the swap, so the
dashboard and controller can both stop without losing their recovery worker.
"""

import asyncio
import copy
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
import zipfile
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

from cryptography.fernet import Fernet

from .app_backups import AppBackups, digest, validate_tar
from .backup_policy import direct
from .deployment import DeploymentError, Deployments
from .docker_names import controller_project
from .host_recovery import HostBackups
from .launcher import instance_lock
from .store import Conflict

PROTOCOL = 1
FILES = {"StackarrPreview.exe", "stackarr-image.tar", "Start-StackarrPreview.ps1", "Start Stackarr.cmd",
         "Recover Stackarr.cmd", "README.txt", "LICENSE", "THIRD-PARTY-NOTICES.md"}
TERMINAL = {"succeeded", "rolled-back", "failed-recovered", "removed"}
ID = re.compile(r"^[a-f0-9]{32}$")
SHA = re.compile(r"^[a-f0-9]{64}$")

# This same fixed probe runs on the host and inside the dashboard. Its sole
# output is a digest; account hashes, sessions and credentials never cross RPC.
FINGERPRINT = '''
import hashlib,json,pathlib,sqlite3
from cryptography.fernet import Fernet
def fingerprint(directory, inventory=False):
 p=pathlib.Path(directory); cipher=Fernet((p/'secrets.key').read_bytes())
 db=sqlite3.connect('file:'+str(p/'stackarr.db')+'?mode=ro',uri=True)
 excluded={'audit','sessions','controller_requests','controller_status_snapshot','setup_handoffs','maintenance_schedule','jobs'}
 only={'deployments','deployment_secrets','deployment_logins','app_updates','controller_media_roots','controller_connections','settings','secrets'}
 result={}
 try:
  tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
  for table in sorted(tables):
   if table in excluded or (inventory and table not in only): continue
   if inventory and table=='settings':
    data=json.loads(db.execute('SELECT data FROM settings WHERE id=1').fetchone()[0]); result['app_settings']={k:data[k] for k in ('integrations','storage')}; continue
   rows=[]
   columns='app,scope' if table=='import_refresh' else '*'
   for row in db.execute('SELECT '+columns+' FROM "'+table.replace('"','""')+'"'):
    if inventory and table=='secrets' and row[0] not in {'plex','sonarr','radarr','prowlarr','qbittorrent','seerr','tautulli','kuma','cleanuparr'} and not row[0].startswith('companions:'): continue
    values=[]
    for value in row:
     if isinstance(value,bytes): value=cipher.decrypt(value).decode()
     if isinstance(value,str):
      try: value=json.loads(value)
      except (ValueError,TypeError): pass
     values.append(value)
    rows.append(values)
   result[table]=sorted(rows,key=lambda r:json.dumps(r,sort_keys=True))
  return hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 finally: db.close()
'''


def fingerprint(directory, inventory=False):
    namespace = {}
    exec(FINGERPRINT, namespace)
    return namespace["fingerprint"](str(directory), inventory)


def snapshot_fingerprint(directory, prefix, inventory=False):
    target = directory / ("probe-" + prefix)
    target.mkdir(exist_ok=True)
    shutil.copyfile(directory / (prefix + ".db"), target / "stackarr.db")
    shutil.copyfile(directory / (prefix + ".key"), target / "secrets.key")
    return fingerprint(target, inventory)


def read(path):
    return json.loads(direct(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    path = direct(path)
    temporary = direct(path.with_suffix(".tmp"))
    try:
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(value, file, sort_keys=True)
            file.flush()
            os.fsync(file.fileno())
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                break
            except PermissionError as exc:
                # Windows readers can briefly deny atomic replacement. Retry
                # only its native access/sharing/lock errors, for at most .75s.
                # Persistent denial still fails without replacing the journal.
                if getattr(exc, 'winerror', None) not in {5, 32, 33} or attempt == 5:
                    raise
                time.sleep(.05 * (attempt + 1))
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass  # A denied path must not replace the original commit error.


def pending(root):
    home = Path(root) / "stackarr-maintenance"
    # Older supervisors only understand update/rollback recovery. Keep retained-
    # data operations out of their pointer so they cannot replay them as updates.
    for name in ("retained-active-job.json", "active-job.json"):
        pointer = home / name
        if not pointer.is_file():
            continue
        identity = read(pointer).get("id", "")
        if not ID.fullmatch(identity):
            raise DeploymentError("Stackarr maintenance state needs inspection.")
        job = read(home / "jobs" / identity / "job.json")
        if job["phase"] not in TERMINAL:
            return job
    return None


def busy(store_root):
    # Candidate controller state is a sibling of the ordinary state folder.
    return pending(Path(store_root).parent.parent) is not None


def package(path):
    path = direct(path)
    manifest = read(path / "manifest.json")
    if (manifest.get("schema") != 1 or manifest.get("maintenance") != {"protocol": PROTOCOL, "state_schema": 1}
            or set(manifest.get("files", {})) != FILES
            or not re.fullmatch(r"stackarr:[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", manifest.get("image", ""))
            or not re.fullmatch(r"sha256:[a-f0-9]{64}", manifest.get("image_id", ""))
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", manifest.get("release", ""))):
        raise DeploymentError("Choose a compatible complete Stackarr update package. Major state migrations are not supported.")
    for name, expected in manifest["files"].items():
        if not SHA.fullmatch(expected) or digest(direct(path / name)) != expected:
            raise DeploymentError("A Stackarr package file is missing or changed. No update was started.")
    return manifest


class Docker:
    context = Deployments.context

    def __init__(self):
        self.runner = subprocess.run
        self.fixed_context = None

    def _call(self, args, **kwargs):
        if self.fixed_context and args[0] != "--context":
            args = ["--context", self.fixed_context, *args]
        return Deployments._call(self, args, **kwargs)


class SelfUpdates:
    def __init__(self, root, package_root=None, docker=None):
        self.root = direct(root)
        self.home = direct(self.root / "stackarr-maintenance")
        self.home.mkdir(exist_ok=True, mode=0o700)
        for name in ("releases", "jobs"):
            direct(self.home / name).mkdir(exist_ok=True, mode=0o700)
        self.docker = docker or Docker()
        self.controller_identity = None
        self.package_root = Path(package_root or os.environ.get("STACKARR_PACKAGE_ROOT", Path(sys.executable).parent))

    @classmethod
    def controller(cls, controller):
        updates = cls(controller.store.root.parent.parent)
        # A review already holds the private RPC lane. Verify this controller
        # locally instead of recursively sending a probe through that same lane.
        updates.controller_identity = {"executable": digest(Path(sys.executable)),
                                       "checking": os.environ.get("STACKARR_UPDATE_CHECKING") == "1"}
        return updates

    def active(self):
        path = self.root / "stackarr-runtime.json"
        return read(path) if path.is_file() else self.adopt()

    def release(self, identity):
        if not SHA.fullmatch(identity):
            raise DeploymentError("Choose a staged Stackarr release.")
        path = direct(self.home / "releases" / identity)
        manifest = package(path)
        if digest(path / "manifest.json") != identity:
            raise DeploymentError("The staged Stackarr release changed.")
        return path, manifest

    def stage_directory(self, source):
        manifest = package(source)
        identity = digest(Path(source) / "manifest.json")
        target = direct(self.home / "releases" / identity)
        if not target.exists():
            with tempfile.TemporaryDirectory(prefix="release-", dir=self.home / "releases") as name:
                stage = Path(name)
                for entry in FILES | {"manifest.json"}:
                    shutil.copyfile(direct(Path(source) / entry), stage / entry)
                package(stage)
                os.replace(stage, target)
        self.release(identity)
        return identity, manifest

    def admit(self, archive):
        if pending(self.root):
            raise Conflict("Finish or recover the current Stackarr update first.")
        with zipfile.ZipFile(direct(archive)) as bundle:
            rows = bundle.infolist()
            names = {Path(row.filename).name for row in rows}
            prefix = {row.filename.split("/")[0] for row in rows}
            if (len(rows) != len(FILES) + 1 or names != FILES | {"manifest.json"} or len(prefix) != 1
                    or any(row.is_dir() or len(row.filename.split("/")) != 2 or "\\" in row.filename
                           or ".." in row.filename.split("/") or row.filename.startswith("/")
                           or (row.external_attr >> 16) & 0o170000 == 0o120000 for row in rows)
                    or sum(row.file_size for row in rows) > 2 * 1024**3):
                raise DeploymentError("The update ZIP contains unsupported files or paths.")
            if shutil.disk_usage(self.home).free < sum(row.file_size for row in rows) * 2 + 50 * 1024**2:
                raise DeploymentError("Free more disk space before staging this update.")
            with tempfile.TemporaryDirectory(prefix="stage-", dir=self.home) as directory:
                target = Path(directory)
                for row in rows:
                    with bundle.open(row) as source, (target / Path(row.filename).name).open("xb") as output:
                        shutil.copyfileobj(source, output)
                identity, manifest = self.stage_directory(target)
        write(self.home / "candidate.json", {"id": identity})
        return {"release": manifest["release"], "id": identity,
                "notice": "Package checksums verified. This is an unsigned public beta; choose only a package you trust."}

    def choose(self):
        script = """Add-Type -AssemblyName System.Windows.Forms
$dialog=New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title='Choose the downloaded Stackarr update ZIP'; $dialog.Filter='Stackarr update (*.zip)|*.zip'
try { if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Write($dialog.FileName) } } finally { $dialog.Dispose() }
"""
        result = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-WindowStyle", "Hidden", "-Command", script],
            capture_output=True, text=True, timeout=180, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise DeploymentError("The update chooser could not open. Existing apps stayed unchanged.")
        return self.admit(result.stdout.strip()) if result.stdout.strip() else {"cancelled": True}

    def dashboard(self, port):
        store = SimpleNamespace(root=self.root / "controller/state")
        service = HostBackups(SimpleNamespace(store=store, _call=self.docker._call), port)
        identity = service.dashboard()
        info = json.loads(self.docker._call(["inspect", identity]))[0]
        return identity, info

    @staticmethod
    def recipe(plan, root, port, controller_port):
        """Do not admit additional services, media mounts or arbitrary Docker knobs."""
        if set(plan) - {"services", "volumes"} or set(plan.get("services", {})) != {"stackarr"} or set(plan.get("volumes", {})) != {"dashboard-state"}:
            raise DeploymentError("This Stackarr dashboard recipe needs manual inspection before self-update.")
        service = plan["services"]["stackarr"]
        allowed = {"image", "init", "read_only", "cap_drop", "security_opt", "restart", "ports", "environment", "volumes", "tmpfs", "labels", "container_name"}
        if "container_name" in service and not re.fullmatch(r"stackarr-controller(?:-[2-9]|-[1-9][0-9]+)?", service["container_name"]):
            raise DeploymentError("Stackarr's container name changed. Self-update was blocked.")
        if (set(service) - allowed or service.get("init") is not True or service.get("read_only") is not True
                or service.get("cap_drop") != ["ALL"] or service.get("security_opt") != ["no-new-privileges:true"]
                or service.get("ports") != [f"127.0.0.1:{port}:8787"]
                or service.get("volumes") != ["dashboard-state:/var/lib/stackarr", {"type": "bind", "source": str(root / "controller/shared"), "target": "/run/stackarr-controller", "read_only": True}]
                or service.get("tmpfs") != ["/tmp:rw,noexec,nosuid,size=32m"]
                or service.get("restart", "unless-stopped") != "unless-stopped"):
            raise DeploymentError("Stackarr's mounts, ports or privileges changed. Self-update was blocked.")
        expected = {"STACKARR_ORIGIN": f"http://localhost:{port}", "STACKARR_CONTROLLER_SHARED": "/run/stackarr-controller", "STACKARR_CONTROLLER_PORT": str(controller_port)}
        if any(service.get("environment", {}).get(k) != v for k, v in expected.items()) or set(service.get("environment", {})) - set(expected) - {"STACKARR_RELEASE_ID", "STACKARR_UPDATE_CHECKING", "STACKARR_LAN_ORIGIN", "STACKARR_LAN_LINKS"}:
            raise DeploymentError("Stackarr's environment changed. Self-update was blocked.")
        from .lan import LanAccess

        try:
            LanAccess(expected["STACKARR_ORIGIN"], service["environment"])
        except (ValueError, TypeError):
            raise DeploymentError("Stackarr's LAN configuration is invalid. Self-update was blocked.") from None
        if set(service.get("labels", {})) - {"io.stackarr.release"}:
            raise DeploymentError("Stackarr's release labels changed.")

    def adopt(self, *, port=None, controller_port=None):
        manifest = package(self.package_root)
        context = self.docker.context()
        controller_port = int(os.environ.get("STACKARR_CONTROLLER_PORT", "28010")) if controller_port is None else controller_port
        port = int(os.environ.get("STACKARR_PORT", "28000")) if port is None else port
        if any(type(value) is not int or not 1 <= value <= 65535 for value in (port, controller_port)):
            raise DeploymentError("Stackarr's saved ports need inspection.")
        plan = read(self.root / "compose.json")
        self.recipe(plan, self.root, port, controller_port)
        identity, info = self.dashboard(port)
        if info["Image"] != manifest["image_id"]:
            raise DeploymentError("The running dashboard does not match this controller's package.")
        project = info["Config"]["Labels"]["com.docker.compose.project"]
        if not controller_project(project):
            raise DeploymentError("This dashboard project is not a supported Stackarr preview.")
        if plan["services"]["stackarr"].get("container_name", project) != project:
            raise DeploymentError("Stackarr's container name does not match its Docker group.")
        volume = next(m["Name"] for m in info["Mounts"] if m["Destination"] == "/var/lib/stackarr")
        self.unshared(volume, identity, project)
        release, _ = self.stage_directory(self.package_root)
        runtime = {"format": 1, "project": project, "context": context, "port": port,
                   "controller_port": controller_port, "release": release, "volume": volume, "plan": plan}
        write(self.root / "stackarr-runtime.json", runtime)
        return runtime

    def unshared(self, volume, container, project):
        row = json.loads(self.docker._call(["volume", "inspect", volume]))[0]
        if row.get("Labels", {}).get("com.docker.compose.project") != project or self.docker._call(["ps", "-aq", "--no-trunc", "--filter", "volume=" + volume]).split() != ([container] if container else []):
            raise DeploymentError("Stackarr's database volume is shared or changed. Self-update was blocked.")

    def jobs(self):
        return sorted([read(p) for p in (self.home / "jobs").glob("*/job.json")], key=lambda r: r["created"], reverse=True)

    def listing(self):
        active = self.active()
        _, current = self.release(active["release"])
        candidate = read(self.home / "candidate.json")["id"] if (self.home / "candidate.json").is_file() else None
        if candidate:
            _, value = self.release(candidate)
            candidate = {"id": candidate, "release": value["release"]}
        return {"current": current["release"], "candidate": candidate,
                "history": [{k: job.get(k) for k in ("id", "action", "phase", "message", "created")} | {"rollback_available": job["action"] in {"update", "rollback", "lan"} and job["phase"] in {"succeeded", "rolled-back"} and job["target"]["release"] == active["release"]} for job in self.jobs()[:20]],
                "recover": (pending(self.root) or {}).get("id"),
                "notice": "Stackarr's dashboard pauses briefly while its controller and database copies are checked. Your media apps continue running. Keep the downloaded package privately; preview releases are unsigned."}

    def protected(self, runtime):
        identity, info = self.dashboard(runtime["port"])
        _, manifest = self.release(runtime["release"])
        if info["Image"] != manifest["image_id"]:
            raise DeploymentError("The active Stackarr image changed. No update was started.")
        if len(info["Mounts"]) != 2 or info["HostConfig"].get("Privileged"):
            raise DeploymentError("The Stackarr container's mounts or privileges changed.")
        self.recipe(read(self.root / "compose.json"), self.root, runtime["port"], runtime["controller_port"])
        self.unshared(runtime["volume"], identity, runtime["project"])
        value = json.loads(self.docker._call(["exec", identity, "python", "-c", FINGERPRINT + "\nprint(json.dumps({'data':fingerprint('/var/lib/stackarr'),'key':hashlib.sha256(pathlib.Path('/var/lib/stackarr/secrets.key').read_bytes()).hexdigest()}))"]))
        return {"dashboard": value["data"], "dashboard_key": value["key"], "controller": fingerprint(self.root / "controller/state"),
                "controller_key": digest(self.root / "controller/state/secrets.key"),
                "inventory": fingerprint(self.root / "controller/state", True),
                "dashboard_inventory": json.loads(self.docker._call(["exec", identity, "python", "-c", FINGERPRINT + "\nprint(json.dumps(fingerprint('/var/lib/stackarr',True)))"])), "container": identity}

    def review(self, action="update", identity=None):
        if action == "repair":
            from .self_repair import SelfRepair

            if identity is not None:
                raise DeploymentError("Review this Stackarr runtime without another operation ID.")
            return SelfRepair(self).review()
        if action in {"remove", "reinstall"}:
            from .self_removal import SelfRemoval

            if identity is not None:
                raise DeploymentError("Review this Stackarr installation without another operation ID.")
            return SelfRemoval(self).review(action)
        if (self.root / "stackarr-removed.json").exists():
            raise Conflict("Stackarr was removed with settings retained. Review reinstall from Start Stackarr first.")
        if action == "recover":
            job = pending(self.root)
            if not job or job["id"] != identity:
                raise Conflict("Choose the interrupted Stackarr update.")
            return {"action": action, "job": identity, "notice": "Recover the previous Stackarr release and its matching database checkpoint. Your app containers and media are untouched."}
        if pending(self.root):
            raise Conflict("Recover the interrupted Stackarr update first.")
        runtime = self.active()
        if self.docker.context() != runtime["context"]:
            raise DeploymentError("Select Stackarr's original local Docker context before updating.")
        before = self.protected(runtime)
        if action == "update":
            candidate = read(self.home / "candidate.json")["id"]
            if candidate == runtime["release"]:
                raise Conflict("This Stackarr release is already active.")
            _, candidate_manifest = self.release(candidate)
            if (runtime["plan"]["services"]["stackarr"]["environment"].get("STACKARR_LAN_ORIGIN")
                    and candidate_manifest.get("lan_access") != 1):
                raise DeploymentError("This release cannot preserve LAN access. Disable the gateway through its rollback plan before installing an older release.")
            target = runtime | {"release": candidate}
            snapshot = None
        elif action == "lan":
            from .lan import LanAccess

            if not isinstance(identity, dict) or set(identity) != {"origin", "links"}:
                raise DeploymentError("Review an exact LAN origin and app links on this computer.")
            if self.release(runtime["release"])[1].get("lan_access") != 1:
                raise DeploymentError("Update to a LAN-capable Stackarr package before reviewing home access.")
            target = copy.deepcopy(runtime)
            environment = target["plan"]["services"]["stackarr"]["environment"]
            environment.update(STACKARR_LAN_ORIGIN=identity["origin"], STACKARR_LAN_LINKS=json.dumps(identity["links"], sort_keys=True))
            LanAccess(environment["STACKARR_ORIGIN"], environment)
            self.recipe(target["plan"], self.root, runtime["port"], runtime["controller_port"])
            if target == runtime:
                raise Conflict("These LAN addresses are already configured.")
            return {"action": "lan", "network": identity, "source": runtime, "target": target,
                    "before": before, "snapshot": None,
                    "notice": "Enable the reviewed HTTPS origin and browser links in Stackarr using checked settings copies and an encrypted rollback checkpoint. Local access stays available. This does not start a gateway or change apps, firewall rules, DNS, certificates or Windows startup."}
        elif action == "rollback":
            job = next((r for r in self.jobs() if r["id"] == identity), None)
            if not job or job["phase"] not in {"succeeded", "rolled-back"} or job["target"]["release"] != runtime["release"]:
                raise Conflict("Choose the active release's latest rollback checkpoint.")
            target, snapshot = job["source"], job["id"]
            self.release(target["release"])
            try:
                with tempfile.TemporaryDirectory(prefix="review-checkpoint-", dir=self.home) as name:
                    self.unpack(job, Path(name))
                    if (before["inventory"] != snapshot_fingerprint(Path(name), "controller", True)
                            or before["dashboard_inventory"] != snapshot_fingerprint(Path(name), "dashboard", True)):
                        raise Conflict("App connections, credentials or ownership receipts changed after this update. They are preserved; this older Stackarr checkpoint cannot be replayed.")
            except Conflict:
                raise
            except Exception:
                raise DeploymentError("The saved Stackarr rollback checkpoint failed verification. Nothing was paused or restored.") from None
        else:
            raise DeploymentError("Choose update, rollback or recovery.")
        return {"action": action, "source": runtime, "target": target, "before": before, "snapshot": snapshot,
                "notice": ("Update the Stackarr dashboard and controller using checked database copies. Failed checks recover the previous release and data. " if action == "update" else "Restore the previous Stackarr release and its database checkpoint. Newer Stackarr preferences will be replaced; a separate safety checkpoint is retained first. Your current Stackarr password and browser sessions stay available. ") + "Media apps keep running; no app volume or media folder is restored."}

    @staticmethod
    def public(review):
        return {"action": review["action"], "notice": review["notice"]}

    def approve(self, review):
        if review["action"] == "recover":
            job = pending(self.root)
            if not job or job["id"] != review["job"]:
                raise Conflict("Review Stackarr recovery again.")
            self.launch(job["id"], recover=True)
            return {"id": job["id"]}
        identity = review["snapshot"] if review["action"] == "rollback" else review.get("network") if review["action"] == "lan" else None
        if self.review(review["action"], identity) != review:
            raise Conflict("Stackarr changed. Review the update again.")
        job = review | {"id": uuid.uuid4().hex, "created": time.time(), "phase": "approved", "message": "Stackarr maintenance approved."}
        directory = self.home / "jobs" / job["id"]
        directory.mkdir(mode=0o700)
        write(directory / "job.json", job)
        pointer = "retained-active-job.json" if review["action"] in {"remove", "reinstall"} else "active-job.json"
        write(self.home / pointer, {"id": job["id"]})
        self.launch(job["id"])
        return {"id": job["id"]}

    def launch(self, identity, recover=False):
        job = read(self.home / "jobs" / identity / "job.json")
        executable = self.release(job.get("supervisor", job["source"]["release"]))[0] / "StackarrPreview.exe"
        subprocess.Popen([str(executable), "--stackarr-maintenance", str(self.root), "--maintenance-job", identity,
                          *( ["--maintenance-recover"] if recover else [])], creationflags=subprocess.CREATE_NO_WINDOW,
                         env=os.environ | {"PYINSTALLER_RESET_ENVIRONMENT": "1"})

    def save(self, job, phase, message):
        job.update(phase=phase, message=message)
        write(self.home / "jobs" / job["id"] / "job.json", job)

    def controller_probe(self, runtime):
        from .controller_enrollment import client
        from .controller_transport import ControllerConnectionError

        deadline = time.monotonic() + 15
        while True:
            try:
                return asyncio.run(client(self.root / "controller/shared", f"https://127.0.0.1:{runtime['controller_port']}",
                                          authority=f"host.docker.internal:{runtime['controller_port']}").request("stackarr-probe"))
            except ControllerConnectionError as exc:
                if exc.status_code not in {429, 503} or time.monotonic() >= deadline:
                    raise
                # This fixed read is safe to repeat with a fresh signed nonce.
                # Browser status polls share the RPC lane; writes are never retried.
                time.sleep(.25)

    @staticmethod
    def listening(port):
        with socket.socket() as connection:
            connection.settimeout(.3)
            return connection.connect_ex(("127.0.0.1", port)) == 0

    def stop_controller(self, job):
        runtime = job["source"]
        if not self.listening(runtime["controller_port"]):
            return
        probe = self.controller_probe(runtime)
        known = [self.release(job[k]["release"])[1]["files"]["StackarrPreview.exe"] for k in ("source", "target")]
        if probe.get("executable") not in known or probe.get("protocol") != PROTOCOL:
            raise DeploymentError("The running controller differs from this reviewed release. It was not stopped.")
        write(self.root / "controller/self-update-stop.json", {"pid": probe["pid"], "job": job["id"]})
        for _ in range(200):
            if not self.listening(runtime["controller_port"]):
                return
            time.sleep(.1)
        raise DeploymentError("The private controller did not stop. Its data was preserved.")

    def controller_start(self, runtime, state=None, checking=False):
        path, manifest = self.release(runtime["release"])
        env = os.environ.copy()
        env.update(STACKARR_PORT=str(runtime["port"]), STACKARR_CONTROLLER_PORT=str(runtime["controller_port"]),
                   STACKARR_PACKAGE_ROOT=str(path), STACKARR_RELEASE_ID=runtime["release"], STACKARR_CONTROLLER_ROOTS="[]",
                   STACKARR_UPDATE_CHECKING="1" if checking else "0", STACKARR_CONTROLLER_STATE=str(state or self.root / "controller/state"))
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        process = subprocess.Popen([str(path / "StackarrPreview.exe"), "--controller-serve", str(self.root / "controller"),
            "--controller-port", str(runtime["controller_port"])], env=env, creationflags=subprocess.CREATE_NO_WINDOW)
        (self.root / "controller.pid").write_text(str(process.pid), encoding="ascii")
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                probe = self.controller_probe(runtime)
                if probe["executable"] != manifest["files"]["StackarrPreview.exe"] or probe["protocol"] != PROTOCOL or probe["checking"] != checking:
                    raise DeploymentError("The controller did not match the approved release.")
                return probe
            except Exception:
                time.sleep(.1)
        raise DeploymentError("The candidate controller did not become ready.")

    def compose(self, runtime, checking=False):
        _, manifest = self.release(runtime["release"])
        plan = copy.deepcopy(runtime["plan"])
        service = plan["services"]["stackarr"]
        service["image"] = manifest["image_id"]
        service.setdefault("labels", {})["io.stackarr.release"] = runtime["release"]
        service["environment"].update(STACKARR_RELEASE_ID=runtime["release"], STACKARR_UPDATE_CHECKING="1" if checking else "0")
        plan["volumes"]["dashboard-state"] = {"external": True, "name": runtime["volume"]}
        self.recipe(plan, self.root, runtime["port"], runtime["controller_port"])
        write(self.root / "compose.json", plan)
        return plan

    def up(self, runtime, checking=False):
        self.compose(runtime, checking)
        self.docker._call(["--context", runtime["context"]["name"], "compose", "--project-name", runtime["project"], "-f", str(self.root / "compose.json"),
                           "up", "-d", "--no-deps", "--wait", "--wait-timeout", "90", "stackarr"], timeout=120)

    def helper(self, runtime, volume, directory, restore=False):
        _, manifest = self.release(runtime["release"])
        if restore:
            validate_tar(directory / "dashboard-volume.tar")
            script = 'test -z "$(ls -A /volume)" && tar -xpf /backup/dashboard-volume.tar -C /volume && chown 10001:10001 /volume && chmod 600 /volume/stackarr.db /volume/secrets.key'
        else:
            script = '''import sqlite3,pathlib,shutil,tarfile
p=pathlib.Path('/volume'); b=pathlib.Path('/backup')
s=sqlite3.connect('file:/volume/stackarr.db?mode=ro',uri=True); d=sqlite3.connect(b/'stackarr.db'); s.backup(d); d.close(); s.close()
shutil.copyfile(p/'secrets.key',b/'secrets.key')
def owner(info):
 info.uid=info.gid=10001; info.uname=info.gname=''; info.mode=0o600; return info
with tarfile.open(b/'dashboard-volume.tar','w') as archive:
 for item in p.iterdir():
  if item.name not in {'stackarr.db','stackarr.db-wal','stackarr.db-shm','stackarr.db-journal','secrets.key'}: archive.add(item,arcname=item.name)
 for name in ('stackarr.db','secrets.key'): archive.add(b/name,arcname=name,filter=owner)
'''
        name = "stackarr-self-update-helper-" + uuid.uuid4().hex
        try:
            self.docker._call(["run", "--name", name, "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL", "--cap-add", "CHOWN", "--cap-add", "DAC_OVERRIDE", "--cap-add", "FOWNER",
                "--security-opt", "no-new-privileges:true", "--user", "0:0", "--entrypoint", "/bin/sh" if restore else "python",
                "--mount", "type=volume,src=" + volume + ",dst=/volume" + ("" if restore else ",readonly"),
                "--mount", "type=bind,src=" + str(directory) + ",dst=/backup" + (",readonly" if restore else ""), manifest["image_id"], "-c", script], timeout=120)
            if not restore:
                validate_tar(directory / "dashboard-volume.tar")
        finally:
            if self.docker._call(["ps", "-aq", "--filter", "name=^/" + name + "$"]).strip():
                self.docker._call(["rm", "-f", name])

    def cipher(self):
        return SimpleNamespace(store=SimpleNamespace(cipher=Fernet(direct(self.root / "controller/state/secrets.key").read_bytes())))

    def snapshot(self, job):
        directory = self.home / "jobs" / job["id"]
        with tempfile.TemporaryDirectory(prefix="checkpoint-", dir=directory) as name:
            stage = Path(name)
            self.helper(job["source"], job["source"]["volume"], stage)
            (stage / "dashboard.db").write_bytes((stage / "stackarr.db").read_bytes())
            (stage / "dashboard.key").write_bytes((stage / "secrets.key").read_bytes())
            with closing(sqlite3.connect(self.root / "controller/state/stackarr.db")) as source, closing(sqlite3.connect(stage / "controller.db")) as target:
                source.backup(target)
            (stage / "controller.key").write_bytes((self.root / "controller/state/secrets.key").read_bytes())
            actual = {"controller": fingerprint(self.root / "controller/state"), "dashboard": fingerprint(stage),
                      "controller_key": digest(self.root / "controller/state/secrets.key"), "dashboard_key": digest(stage / "secrets.key"),
                      "inventory": fingerprint(self.root / "controller/state", True), "dashboard_inventory": fingerprint(stage, True), "container": job["before"]["container"]}
            changed = actual != job["before"]
            job["before"] = actual
            archive = stage / "snapshot.tar"
            with tarfile.open(archive, "w") as tar:
                for entry in ("dashboard.db", "dashboard.key", "dashboard-volume.tar", "controller.db", "controller.key"):
                    tar.add(stage / entry, arcname=entry)
            partial = stage / "checkpoint.partial"
            AppBackups.crypt(self.cipher(), archive, partial)
            verified = stage / "verified-snapshot.tar"
            AppBackups.crypt(self.cipher(), partial, verified, decrypt=True)
            if digest(archive) != digest(verified):
                raise DeploymentError("Stackarr's encrypted checkpoint could not be verified. Original data is retained.")
            with (directory / "recovery.key").open("xb") as output:
                output.write((self.root / "controller/state/secrets.key").read_bytes())
            os.chmod(directory / "recovery.key", 0o600)
            os.replace(partial, directory / "checkpoint.enc")
            job["checkpoint_hash"] = digest(directory / "checkpoint.enc")
        self.save(job, "checkpoint-saved", "Encrypted Stackarr safety checkpoint verified before candidate startup.")
        if changed:
            raise Conflict("Saved settings changed before the pause. The latest settings were preserved; review the update again.")

    def unpack(self, job, destination):
        directory = self.home / "jobs" / job["id"]
        if digest(directory / "checkpoint.enc") != job["checkpoint_hash"]:
            raise DeploymentError("The Stackarr recovery checkpoint changed. No database was restored.")
        cipher = SimpleNamespace(store=SimpleNamespace(cipher=Fernet(direct(directory / "recovery.key").read_bytes())))
        AppBackups.crypt(cipher, directory / "checkpoint.enc", destination / "snapshot.tar", decrypt=True)
        with tarfile.open(destination / "snapshot.tar") as tar:
            rows = tar.getmembers()
            if len(rows) != 5 or {r.name for r in rows} != {"dashboard.db", "dashboard.key", "dashboard-volume.tar", "controller.db", "controller.key"} or any(not r.isfile() for r in rows):
                raise DeploymentError("The Stackarr checkpoint has unsupported contents.")
            for row in rows:
                with tar.extractfile(row) as source, (destination / row.name).open("xb") as output:
                    shutil.copyfileobj(source, output)
        for prefix in ("controller", "dashboard"):
            with closing(sqlite3.connect(destination / (prefix + ".db"))) as db:
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise DeploymentError("A Stackarr recovery database is damaged.")
        validate_tar(destination / "dashboard-volume.tar")

    def candidate_state(self, job, snapshot):
        state = direct(self.root / "controller" / ("state-candidate-" + job["id"]))
        state.mkdir(mode=0o700)
        shutil.copyfile(snapshot / "controller.db", state / "stackarr.db")
        shutil.copyfile(snapshot / "controller.key", state / "secrets.key")
        original = direct(self.root / "controller/state/deployments")
        target = state / "deployments"
        target.mkdir()
        if original.exists():
            for directory in original.iterdir():
                if not ID.fullmatch(directory.name):
                    raise DeploymentError("A controller receipt folder needs inspection.")
                direct(directory)
                (target / directory.name).mkdir()
                shutil.copyfile(direct(directory / "compose.json"), target / directory.name / "compose.json")
        return state

    def retain_account(self, snapshot, current):
        """Compatible schema only: preserve the current owner and live sessions on rollback."""
        with closing(sqlite3.connect(current / "dashboard.db")) as source, closing(sqlite3.connect(snapshot / "dashboard.db")) as target:
            for table in ("account", "sessions"):
                rows = source.execute("SELECT * FROM " + table).fetchall()
                target.execute("DELETE FROM " + table)
                if rows:
                    target.executemany("INSERT INTO " + table + " VALUES(" + ",".join("?" for _ in rows[0]) + ")", rows)
            target.commit()
        original = snapshot / "dashboard-volume.tar"
        replacement = snapshot / "dashboard-volume-merged.tar"
        with tarfile.open(original) as source, tarfile.open(replacement, "w") as target:
            for member in source:
                if member.name.removeprefix("./") == "stackarr.db":
                    member = target.gettarinfo(snapshot / "dashboard.db", "stackarr.db")
                    member.uid = member.gid = 10001
                    member.mode = 0o600
                    with (snapshot / "dashboard.db").open("rb") as file:
                        target.addfile(member, file)
                else:
                    stream = source.extractfile(member) if member.isfile() else None
                    try:
                        target.addfile(member, stream)
                    finally:
                        if stream:
                            stream.close()
        validate_tar(replacement)
        os.replace(replacement, original)

    def load_image(self, release):
        path, manifest = self.release(release)
        self.docker._call(["load", "--input", str(path / "stackarr-image.tar")], timeout=180)
        if self.docker._call(["image", "inspect", manifest["image"], "--format", "{{.Id}}"]).strip() != manifest["image_id"]:
            raise DeploymentError("The downloaded Stackarr image does not match its package.")

    def health(self, runtime, expected, checking):
        import httpx

        _, info = self.dashboard(runtime["port"])
        _, manifest = self.release(runtime["release"])
        if (info["Image"] != manifest["image_id"] or info["State"].get("Health", {}).get("Status") != "healthy"
                or next(m["Name"] for m in info["Mounts"] if m["Destination"] == "/var/lib/stackarr") != runtime["volume"]):
            raise DeploymentError("The Stackarr dashboard failed release or database-volume checks.")
        with httpx.Client(trust_env=False, timeout=5) as client:
            response = client.get(f"http://127.0.0.1:{runtime['port']}/healthz", headers={"Host": f"localhost:{runtime['port']}"})
            if response.status_code != 200:
                raise DeploymentError("The Stackarr dashboard did not pass its HTTP health check.")
        actual = json.loads(self.docker._call(["exec", info["Id"], "python", "-c", FINGERPRINT + "\nprint(json.dumps({'data':fingerprint('/var/lib/stackarr'),'key':hashlib.sha256(pathlib.Path('/var/lib/stackarr/secrets.key').read_bytes()).hexdigest()}))"]))
        probe = self.controller_probe(runtime)
        if (actual["data"] != expected["dashboard"] or actual["key"] != expected["dashboard_key"]
                or probe.get("key_fingerprint") != expected["controller_key"]
                or probe.get("fingerprint") != expected["controller"] or probe.get("checking") != checking):
            raise DeploymentError("Stackarr's account, credentials or saved settings changed during candidate startup.")

    def stop_dashboard(self, runtime):
        name = runtime["plan"]["services"]["stackarr"].get("container_name", runtime["project"] + "-stackarr-1")
        rows = self.docker._call(["ps", "-aq", "--no-trunc", "--filter", "name=^/" + name + "$"]).split()
        if not rows:
            return
        info = json.loads(self.docker._call(["inspect", rows[0]]))[0]
        known_images = {package(self.release(r)[0])["image_id"] for r in [runtime["release"]]}
        job = pending(self.root)
        if job:
            known_images.update(self.release(job[k]["release"])[1]["image_id"] for k in ("source", "target"))
        volumes = {runtime["volume"]}
        if job:
            volumes.update(job[k]["volume"] for k in ("source", "target"))
        if (info["Config"]["Labels"].get("com.docker.compose.project") != runtime["project"]
                or info["Config"]["Labels"].get("com.docker.compose.service") != "stackarr"
                or info["Image"] not in known_images or len(info["Mounts"]) != 2
                or next((m.get("Name") for m in info["Mounts"] if m["Destination"] == "/var/lib/stackarr"), None) not in volumes):
            raise DeploymentError("The dashboard container changed. It was not stopped.")
        if info["State"].get("Paused"):
            self.docker._call(["unpause", info["Id"]])
        self.docker._call(["stop", "--timeout", "60", info["Id"]], timeout=90)

    def restore_controller(self, snapshot):
        state = direct(self.root / "controller/state")
        # Both controller processes are stopped. Replace only its database/key;
        # app receipts, app backups, media roots and enrollment remain in place.
        for name in ("stackarr.db-wal", "stackarr.db-shm"):
            direct(state / name).unlink(missing_ok=True)
        for original, name in (("controller.db", "stackarr.db"), ("controller.key", "secrets.key")):
            target = direct(state / name)
            temporary = direct(state / (name + ".self-update"))
            shutil.copyfile(snapshot / original, temporary)
            os.replace(temporary, target)

    def recover(self, job, repair_checked=False):
        if job["action"] == "repair" and not repair_checked:
            from .self_repair import SelfRepair

            return SelfRepair(self).recover(job)
        if job["action"] == "reinstall":
            from .self_removal import SelfRemoval

            return SelfRemoval(self).recover_reinstall(job)
        self.save(job, "recovering", "Recovering the previous Stackarr release and database checkpoint.")
        self.stop_controller(job)
        self.stop_dashboard(job["source"])
        if job.get("checkpoint_hash"):
            with tempfile.TemporaryDirectory(prefix="restore-", dir=self.home / "jobs" / job["id"]) as name:
                self.unpack(job, Path(name))
                self.restore_controller(Path(name))
        source = job["source"]
        self.load_image(source["release"])
        write(self.root / "stackarr-runtime.json", source)
        self.controller_start(source)
        self.up(source)
        if job.get("checkpoint_hash"):
            self.health(source, job["before"], False)
        self.save(job, "failed-recovered", "Stackarr repair did not complete. Its original release, account, settings and backups are working again; media apps stayed unchanged." if job["action"] == "repair" else "Stackarr update did not complete. The previous release, account and saved settings are working again. Media apps stayed unchanged.")

    def execute(self, identity, recover=False):
        if not ID.fullmatch(identity):
            raise DeploymentError("Choose a saved Stackarr operation.")
        lock = instance_lock(self.home / "worker-lock")
        try:
            job = read(self.home / "jobs" / identity / "job.json")
            if job["phase"] in TERMINAL:
                return
            if self.docker.context() != job["source"]["context"]:
                raise DeploymentError("Select Stackarr's original local Docker context before maintenance.")
            self.docker.fixed_context = job["source"]["context"]["name"]
            job["worker_pid"] = os.getpid()
            write(self.home / "jobs" / identity / "job.json", job)
            if job["action"] == "remove":
                from .self_removal import SelfRemoval

                SelfRemoval(self).execute_remove(job, recover or job["phase"] != "approved")
                return
            if recover or job["phase"] != "approved":
                try:
                    self.recover(job)
                except Exception:
                    self.save(job, "needs-recovery", "Stackarr recovery needs attention. Restore Docker/storage availability and reopen Start Stackarr. App volumes and media have not been restored or deleted.")
                return
            if job["action"] == "repair":
                from .self_repair import SelfRepair

                try:
                    SelfRepair(self).preflight(job)
                except Exception as exc:
                    job["failure"] = str(exc) if isinstance(exc, (DeploymentError, Conflict)) else type(exc).__name__
                    self.save(job, "failed-recovered", "Stackarr repair was cancelled before downtime. Restore Docker/storage access or check its saved ports, then review again. Existing settings and apps were preserved.")
                    return
            try:
                if job["action"] == "reinstall":
                    from .self_removal import SelfRemoval

                    SelfRemoval(self).preflight_reinstall(job)
                self.load_image(job["target"]["release"])
                self.save(job, "stopping", "Pausing only Stackarr; your media apps keep running.")
                self.stop_controller(job)
                self.stop_dashboard(job["source"])
                self.snapshot(job)
                with tempfile.TemporaryDirectory(prefix="candidate-", dir=self.home / "jobs" / identity) as name:
                    snapshot = Path(name)
                    if job["action"] == "rollback":
                        previous = read(self.home / "jobs" / job["snapshot"] / "job.json")
                        self.unpack(previous, snapshot)
                        current = snapshot / "current-account"
                        current.mkdir()
                        self.unpack(job, current)
                        self.retain_account(snapshot, current)
                        expected = previous["before"] | {"dashboard": snapshot_fingerprint(snapshot, "dashboard")}
                    else:
                        self.unpack(job, snapshot)
                        expected = job["before"]
                    state = self.candidate_state(job, snapshot)
                    if fingerprint(state) != expected["controller"]:
                        raise DeploymentError("The controller checkpoint no longer matches the reviewed settings.")
                    volume = "stackarr-self-update-" + identity
                    if volume in self.docker._call(["volume", "ls", "-q"]).split():
                        raise DeploymentError("The new Stackarr database volume already exists. It was not adopted.")
                    self.docker._call(["volume", "create", "--label", "com.docker.compose.project=" + job["source"]["project"],
                        "--label", "io.stackarr.self-update=" + identity, volume])
                    dash = snapshot / "dashboard"
                    dash.mkdir()
                    shutil.copyfile(snapshot / "dashboard.db", dash / "stackarr.db")
                    shutil.copyfile(snapshot / "dashboard.key", dash / "secrets.key")
                    shutil.copyfile(snapshot / "dashboard-volume.tar", dash / "dashboard-volume.tar")
                    self.helper(job["source"], volume, dash, restore=True)
                    job["target"] = job["target"] | {"volume": volume}
                    self.save(job, "checking-candidate", "Checking both candidate components against isolated database copies.")
                    self.controller_start(job["target"], state, True)
                    self.up(job["target"], True)
                    self.health(job["target"], expected, True)
                    if job["action"] in {"reinstall", "repair"}:
                        from .self_removal import SelfRemoval

                        SelfRemoval(self).check_files(job, job["target"])
                    self.save(job, "committing", "Candidate checks passed; committing the verified Stackarr release.")
                    self.stop_controller(job)
                    self.stop_dashboard(job["target"])
                    shutil.copyfile(state / "stackarr.db", snapshot / "controller.db")
                    shutil.copyfile(state / "secrets.key", snapshot / "controller.key")
                    self.restore_controller(snapshot)
                    if job["action"] != "reinstall":
                        write(self.root / "stackarr-runtime.json", job["target"])
                    self.controller_start(job["target"])
                    self.up(job["target"])
                    self.health(job["target"], expected, False)
                    if job["action"] in {"reinstall", "repair"}:
                        SelfRemoval(self).check_files(job, job["target"])
                    job["after"] = {**expected, "inventory": fingerprint(self.root / "controller/state", True)}
                if job["action"] == "reinstall":
                    from .self_removal import SelfRemoval

                    write(self.root / "stackarr-runtime.json", job["target"])
                    SelfRemoval(self).finish_reinstall(job)
                self.save(job, "rolled-back" if job["action"] == "rollback" else "succeeded", "Stackarr runtime repaired using its saved release. Account, credentials, settings and backups verified; media apps stayed unchanged." if job["action"] == "repair" else "Stackarr reinstalled. Account, credentials, settings and retained backups verified; media apps stayed unchanged." if job["action"] == "reinstall" else "Stackarr rollback verified; the safety checkpoint is retained." if job["action"] == "rollback" else "Stackarr dashboard and controller updated. Account, credentials and settings verified; rollback is available.")
            except Exception as exc:
                job["failure_phase"] = job["phase"]
                job["failure"] = str(exc) if isinstance(exc, (DeploymentError, Conflict)) else type(exc).__name__
                try:
                    self.recover(job)
                except Exception:
                    self.save(job, "needs-recovery", "Stackarr could not confirm recovery. Reopen Start Stackarr after checking Docker and storage. Previous releases and encrypted checkpoints are retained; app volumes and media are untouched.")
        finally:
            lock.close()

    def start(self):
        job = pending(self.root)
        if job:
            self.execute(job["id"], recover=True)
            if pending(self.root):
                raise DeploymentError("Stackarr still needs recovery. Check Docker and storage, then reopen it.")
        if (self.root / "stackarr-removed.json").exists():
            from .self_removal import StackarrRemoved

            raise StackarrRemoved("Stackarr is removed with its settings retained. Reopen Start Stackarr to review reinstall.")
        runtime = self.active()
        manifest = self.release(runtime["release"])[1]
        if self.docker.context() != runtime["context"]:
            raise DeploymentError("Select Stackarr's original local Docker context before startup.")
        self.docker.fixed_context = runtime["context"]["name"]
        plan = read(self.root / "compose.json")
        self.recipe(plan, self.root, runtime["port"], runtime["controller_port"])
        volumes = plan["volumes"]["dashboard-state"]
        allowed_volume = {"external": True, "name": runtime["volume"]}
        if (plan["services"]["stackarr"]["image"] not in {manifest["image"], manifest["image_id"]}
                or (volumes != allowed_volume and not (volumes == {} and runtime["volume"] == runtime["project"] + "_dashboard-state"))):
            raise DeploymentError("Stackarr's saved image or database volume changed. Startup preserved the edited recipe for inspection.")
        if not self.listening(runtime["controller_port"]):
            self.controller_start(runtime)
        else:
            probe = self.controller_probe(runtime)
            if probe.get("executable") != manifest["files"]["StackarrPreview.exe"] or probe.get("checking") is not False:
                raise DeploymentError("The active controller does not match the saved release. Its data was preserved; use the saved maintenance recovery.")
        if self.listening(runtime["port"]):
            _, info = self.dashboard(runtime["port"])
            if info["Image"] != manifest["image_id"] or next(m["Name"] for m in info["Mounts"] if m["Destination"] == "/var/lib/stackarr") != runtime["volume"]:
                raise DeploymentError("The running Stackarr dashboard changed. Startup did not overwrite it.")
        self.up(runtime)
        return f"http://localhost:{runtime['port']}"
