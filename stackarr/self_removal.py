"""Retained-data Stackarr removal and reviewed reinstall, using its supervisor."""

import copy
import hashlib
import json
import os
import re
import tarfile
import tempfile
from pathlib import Path

from .app_backups import digest
from .backup_policy import direct
from .deployment import DeploymentError
from .ports import available
from .self_update import ID, fingerprint, pending, read, write
from .store import Conflict

FILES_PROBE = '''
import hashlib,json,os,pathlib
p=pathlib.Path('/var/lib/stackarr'); rows=[]
excluded={'stackarr.db','stackarr.db-wal','stackarr.db-shm','stackarr.db-journal','secrets.key'}
for item in p.rglob('*'):
 name=item.relative_to(p).as_posix()
 if name in excluded: continue
 if item.is_symlink(): rows.append([name,'link',os.readlink(item)])
 elif item.is_file():
  with item.open('rb') as source: value=hashlib.file_digest(source,'sha256').hexdigest()
  rows.append([name,'file',value])
print(hashlib.sha256(json.dumps(sorted(rows),separators=(',',':')).encode()).hexdigest())
'''


def archive_files(path):
    rows = []
    excluded = {"stackarr.db", "stackarr.db-wal", "stackarr.db-shm", "stackarr.db-journal", "secrets.key"}
    with tarfile.open(path) as archive:
        for member in archive:
            name = member.name.removeprefix("./")
            if name in excluded:
                continue
            if member.issym():
                rows.append([name, "link", member.linkname])
            elif member.isfile() or member.islnk():
                with archive.extractfile(member) as source:
                    rows.append([name, "file", hashlib.file_digest(source, "sha256").hexdigest()])
    return hashlib.sha256(json.dumps(sorted(rows), separators=(",", ":")).encode()).hexdigest()


class StackarrRemoved(DeploymentError):
    pass


class SelfRemoval:
    def __init__(self, updates):
        self.updates, self.root = updates, updates.root
        self.marker = direct(self.root / "stackarr-removed.json")

    def container(self, runtime):
        if not re.fullmatch(r"stackarr-(?:preview|plex-lab)-[a-f0-9]{12}", runtime["project"]):
            raise DeploymentError("This is not an owned Stackarr preview project.")
        ids = self.updates.docker._call(["ps", "-aq", "--no-trunc", "--filter", "name=^/" + runtime["project"] + "-stackarr-1$"]).split()
        if not ids:
            return None
        if len(ids) != 1 or not re.fullmatch(r"[a-f0-9]{64}", ids[0]):
            raise DeploymentError("Stackarr's container identity is ambiguous. Nothing was removed.")
        return json.loads(self.updates.docker._call(["inspect", ids[0]]))[0]

    def context(self, runtime):
        if self.updates.docker.context() != runtime["context"]:
            raise DeploymentError("Select Stackarr's original local Docker context before maintenance.")
        self.updates.docker.fixed_context = runtime["context"]["name"]

    def enrollment(self):
        return {name: digest(direct(self.root / "controller" / name)) for name in ("controller.key", "shared/rpc.key", "shared/controller.crt")}

    def files(self, runtime):
        info = self.container(runtime)
        if not info or not info["State"].get("Running"):
            raise DeploymentError("Stackarr must be running for its configuration-file check.")
        self.resources(runtime, info)
        return self.updates.docker._call(["exec", info["Id"], "python", "-c", FILES_PROBE]).strip()

    def check_files(self, job, runtime):
        if self.files(runtime) != job["preserved_files"]:
            raise DeploymentError("Stackarr's retained backup or configuration files changed during reinstall.")

    @staticmethod
    def container_recipe(info):
        return hashlib.sha256(json.dumps({k: info[k] for k in ("Config", "HostConfig", "Mounts")}, sort_keys=True).encode()).hexdigest()

    def resources(self, runtime, info=None):
        u = self.updates
        state = direct(self.root / "controller/state")
        if not state.is_dir() or any(not direct(state / name).is_file() for name in ("stackarr.db", "secrets.key")):
            raise DeploymentError("Stackarr's retained controller settings are unavailable. No data was replaced.")
        u.recipe(runtime["plan"], self.root, runtime["port"], runtime["controller_port"])
        _, manifest = u.release(runtime["release"])
        image = json.loads(u.docker._call(["image", "inspect", manifest["image_id"]]))[0]
        if image["Id"] != manifest["image_id"] or image.get("Os") != "linux" or image.get("Architecture") != "amd64":
            raise DeploymentError("The retained Stackarr image is missing or changed. Its data was preserved.")
        u.unshared(runtime["volume"], info["Id"] if info else None, runtime["project"])
        volume = json.loads(u.docker._call(["volume", "inspect", runtime["volume"]]))[0]
        if volume.get("Driver") != "local" or volume.get("Scope") != "local" or volume.get("Options"):
            raise DeploymentError("Stackarr's settings volume changed. No volume was removed or restored.")
        network_name = runtime["project"] + "_default"
        network = json.loads(u.docker._call(["network", "inspect", network_name]))[0]
        labels = network.get("Labels") or {}
        defaults = {"com.docker.network.enable_ipv4": "true", "com.docker.network.enable_ipv6": "false"}
        if (network.get("Driver") != "bridge" or labels.get("com.docker.compose.project") != runtime["project"]
                or labels.get("com.docker.compose.network") != "default"
                or any(defaults.get(k) != v for k, v in (network.get("Options") or {}).items())):
            raise DeploymentError("Stackarr's private network changed. Nothing was removed.")
        if info:
            config, host, service = info["Config"], info["HostConfig"], runtime["plan"]["services"]["stackarr"]
            defaults = image.get("Config") or {}
            env = dict(v.split("=", 1) for v in defaults.get("Env", []) if "=" in v)
            env.update(service["environment"])
            actual = dict(v.split("=", 1) for v in config.get("Env", []) if "=" in v)
            # Adopted previews may predate explicit release/checking environment.
            if "STACKARR_RELEASE_ID" in actual:
                env.update(STACKARR_RELEASE_ID=runtime["release"], STACKARR_UPDATE_CHECKING=actual.get("STACKARR_UPDATE_CHECKING"))
            mounts = {v["Destination"]: v for v in info["Mounts"]}
            state, enrollment = mounts.get("/var/lib/stackarr", {}), mounts.get("/run/stackarr-controller", {})
            source = enrollment.get("Source", "")
            match = re.fullmatch(r"/(?:run/desktop/mnt/host|host_mnt)/([a-zA-Z])/(.*)", source)
            if os.name == "nt" and match:
                source = match[1] + ":/" + match[2]
            labels = config.get("Labels") or {}
            if (info["Image"] != manifest["image_id"] or actual != env
                    or actual.get("STACKARR_UPDATE_CHECKING", "0") not in {"0", "1"}
                    or config.get("Entrypoint") != defaults.get("Entrypoint") or config.get("Cmd") != defaults.get("Cmd")
                    or config.get("User", "") != defaults.get("User", "")
                    or labels.get("com.docker.compose.project") != runtime["project"] or labels.get("com.docker.compose.service") != "stackarr"
                    or labels.get("io.stackarr.release", runtime["release"]) != runtime["release"]
                    or len(info["Mounts"]) != 2 or state.get("Type") != "volume" or state.get("Name") != runtime["volume"] or state.get("RW") is not True
                    or enrollment.get("Type") != "bind" or enrollment.get("RW") is not False
                    or os.path.normcase(os.path.normpath(source)) != os.path.normcase(os.path.normpath(str(self.root / "controller/shared")))
                    or host.get("Privileged") or host.get("ReadonlyRootfs") is not True or host.get("Init") is not True
                    or host.get("CapDrop") != ["ALL"] or host.get("CapAdd") or host.get("Devices") or host.get("DeviceRequests")
                    or host.get("ExtraHosts") or host.get("Links") or host.get("AutoRemove")
                    or host.get("SecurityOpt") != ["no-new-privileges:true"] or host.get("Tmpfs") != {"/tmp": "rw,noexec,nosuid,size=32m"}
                    or host.get("RestartPolicy", {}).get("Name") != service.get("restart", "no")
                    or host.get("PortBindings") != {"8787/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(runtime["port"])}]}
                    or host.get("NetworkMode") != network_name or host.get("IpcMode") != "private" or host.get("PidMode") or host.get("UsernsMode")
                    or set(info["NetworkSettings"].get("Networks", {})) != {network_name}
                    or info["State"].get("Paused") or info["State"].get("Restarting")):
                raise DeploymentError("Stackarr's container, environment, mounts or privileges changed. Nothing was removed or restored.")
        return {"volume": hashlib.sha256(json.dumps(volume, sort_keys=True).encode()).hexdigest(), "network": network["Id"], "enrollment": self.enrollment()}

    @staticmethod
    def guard(identity):
        return {"stackarr_removed": identity, "notice": "Settings retained. Open Start Stackarr from a removal-capable package to review reinstall."}

    def saved(self, identity=None):
        value = read(self.marker) if self.marker.exists() else {"format": 1, "job": identity}
        if value.get("format") != 1 or not ID.fullmatch(value.get("job") or ""):
            raise DeploymentError("The saved Stackarr removal needs inspection. Data was preserved.")
        if identity and value["job"] != identity:
            raise DeploymentError("A different saved Stackarr removal needs inspection.")
        job = read(self.updates.home / "jobs" / value["job"] / "job.json")
        if job.get("action") != "remove" or job.get("id") != value["job"]:
            raise DeploymentError("The saved removal belongs to another operation.")
        return job

    def retained(self, job):
        u, runtime = self.updates, job["source"]
        if u.active() != runtime or self.container(runtime):
            raise DeploymentError("Another Stackarr runtime occupies this installation. It was not replaced.")
        if self.resources(runtime) != job["resources"]:
            raise DeploymentError("Stackarr's retained settings, enrollment or network changed. Nothing was overwritten.")
        with tempfile.TemporaryDirectory(prefix="retained-check-", dir=u.home) as name:
            stage = Path(name)
            u.helper(runtime, runtime["volume"], stage)
            if archive_files(stage / "dashboard-volume.tar") != job["preserved_files"]:
                raise DeploymentError("Retained Stackarr backup/configuration files changed. They were not overwritten.")
            before = job["before"]
            if (fingerprint(stage) != before["dashboard"] or digest(stage / "secrets.key") != before["dashboard_key"]
                    or fingerprint(self.root / "controller/state") != before["controller"]
                    or digest(self.root / "controller/state/secrets.key") != before["controller_key"]):
                raise DeploymentError("Retained Stackarr settings changed. Reinstall preserved them; inspect the saved checkpoint before recovery.")
        return job["before"]

    def review(self, action):
        u = self.updates
        if pending(self.root):
            raise Conflict("Recover the current Stackarr maintenance before another action.")
        runtime = u.active()
        self.context(runtime)
        if action == "remove":
            if self.marker.exists():
                raise Conflict("Stackarr is already removed with settings retained.")
            info = self.container(runtime)
            if not info or not info["State"].get("Running"):
                raise DeploymentError("Open this installation's working dashboard before reviewing removal.")
            u.recipe(read(self.root / "compose.json"), self.root, runtime["port"], runtime["controller_port"])
            resources, before = self.resources(runtime, info), u.protected(runtime)
            probe = u.controller_identity or u.controller_probe(runtime)
            if probe.get("executable") != u.release(runtime["release"])[1]["files"]["StackarrPreview.exe"] or probe.get("checking"):
                raise DeploymentError("The private controller does not match the active release.")
            snapshot, removal = None, None
            recipe = self.container_recipe(info)
            preserved_files = self.files(runtime)
            notice = "Remove only Stackarr's dashboard container and stop its private controller. A verified encrypted safety checkpoint is saved first. Keep the Stackarr state folder: your account, settings, keys, generated logins, app receipts and backups are retained. Your media apps keep running; media and downloads are untouched. Scheduled backups pause until you reinstall. Reopen Start Stackarr from this package to review reinstall."
        elif action == "reinstall":
            saved = self.saved()
            if read(self.root / "compose.json") != self.guard(saved["id"]):
                raise DeploymentError("The saved removal recipe changed. Nothing was overwritten.")
            if not available(runtime["port"]) or not available(runtime["controller_port"]):
                raise Conflict("A saved Stackarr port is occupied. Free it before reinstall; the other service was not stopped.")
            before, resources, snapshot, removal = self.retained(saved), saved["resources"], None, saved["id"]
            recipe = None
            preserved_files = saved["preserved_files"]
            with tempfile.TemporaryDirectory(prefix="reinstall-review-", dir=u.home) as name:
                u.unpack(saved, Path(name))
            notice = "Reinstall the same saved Stackarr release using checked copies of its retained settings. Your Stackarr password, connections, app logins and backups are preserved. Failed checks keep Stackarr removed and retain the checkpoint. Your existing media apps keep running; no app container, volume or media folder is recreated or restored."
        else:
            raise DeploymentError("Choose retained-data removal or reinstall.")
        return {"action": action, "source": runtime, "target": copy.deepcopy(runtime), "before": before, "resources": resources,
                "snapshot": snapshot, "removal": removal, "container_recipe": recipe, "preserved_files": preserved_files, "notice": notice}

    def finish_removed(self, job):
        u = self.updates
        self.retained(job)
        if u.listening(job["source"]["controller_port"]):
            raise DeploymentError("The controller port is still in use. Its process was not guessed or killed.")
        write(self.root / "compose.json", self.guard(job["id"]))
        write(self.marker, {"format": 1, "job": job["id"]})
        u.save(job, "succeeded", "Stackarr removed; account, settings, keys and backups retained. Media apps keep running. Reopen Start Stackarr to review reinstall.")

    def recover_remove(self, job):
        u, runtime = self.updates, job["source"]
        info = self.container(runtime)
        if not info:
            if not job.get("checkpoint_hash"):
                raise DeploymentError("The dashboard disappeared before a verified checkpoint. Inspect retained data before recovery.")
            with tempfile.TemporaryDirectory(prefix="removal-recovery-", dir=u.home) as name:
                u.unpack(job, Path(name))
            self.finish_removed(job)
            return
        if info["Id"] != job["before"]["container"] or self.resources(runtime, info) != job["resources"]:
            raise DeploymentError("Another container or changed settings occupies Stackarr's identity. It was not stopped.")
        u.compose(runtime)
        if not u.listening(runtime["controller_port"]):
            u.controller_start(runtime)
        if not info["State"].get("Running"):
            u.docker._call(["start", info["Id"]], timeout=60)
        u.health(runtime, job["before"], False)
        if self.marker.exists():
            if read(self.marker).get("job") != job["id"]:
                raise DeploymentError("A different saved removal needs inspection.")
            self.marker.unlink()
        u.save(job, "failed-recovered", "Stackarr removal did not complete. Its original dashboard, account and settings are working again. No media app or data was removed.")

    def execute_remove(self, job, recover=False):
        u, runtime = self.updates, job["source"]
        try:
            if recover:
                self.recover_remove(job)
                return
            info = self.container(runtime)
            if not info or not info["State"].get("Running") or info["Id"] != job["before"]["container"] or self.resources(runtime, info) != job["resources"]:
                raise Conflict("Stackarr changed after removal review. Review again.")
            if self.container_recipe(info) != job["container_recipe"]:
                raise Conflict("The reviewed Stackarr container changed. Nothing was removed.")
            if u.protected(runtime) != job["before"]:
                raise Conflict("Stackarr settings changed after review. No data was removed.")
            u.save(job, "stopping", "Pausing only Stackarr before its encrypted safety checkpoint; media apps keep running.")
            write(self.root / "compose.json", self.guard(job["id"]))
            u.stop_controller(job)
            u.stop_dashboard(runtime)
            info = self.container(runtime)
            if not info or info["Id"] != job["before"]["container"] or info["State"].get("Running") or info["State"].get("ExitCode") == 137:
                raise DeploymentError("Stackarr did not stop cleanly. Its container and settings were retained.")
            u.snapshot(job)
            with tempfile.TemporaryDirectory(prefix="verify-removal-", dir=u.home) as name:
                u.unpack(job, Path(name))
                if archive_files(Path(name) / "dashboard-volume.tar") != job["preserved_files"]:
                    raise Conflict("Stackarr's configuration files changed before the pause. They were preserved; review removal again.")
            info = self.container(runtime)
            if not info or info["Id"] != job["before"]["container"] or self.resources(runtime, info) != job["resources"] or self.container_recipe(info) != job["container_recipe"]:
                raise Conflict("Stackarr's retained storage changed before removal.")
            u.save(job, "removing-stackarr", "Removing only the verified Stackarr dashboard container; all settings and media apps remain.")
            # Older launchers reject this deliberate non-Compose receipt instead
            # of silently recreating a removed dashboard from retained data.
            write(self.root / "compose.json", self.guard(job["id"]))
            u.docker._call(["rm", info["Id"]])
            self.finish_removed(job)
        except Exception as exc:
            job["failure_phase"] = job["phase"]
            job["failure"] = str(exc) if isinstance(exc, (DeploymentError, Conflict)) else type(exc).__name__
            if job["phase"] == "approved":
                u.save(job, "failed-recovered", "Stackarr removal was cancelled before downtime because the reviewed runtime changed. Its current settings and running state were preserved.")
                return
            try:
                self.recover_remove(job)
            except Exception:
                u.save(job, "needs-recovery", "Stackarr removal needs attention. Check Docker and storage, then reopen Start Stackarr. Settings checkpoints, media apps and media are retained.")

    def preflight_reinstall(self, job):
        saved = self.saved(job["removal"])
        if read(self.root / "compose.json") != self.guard(saved["id"]):
            raise Conflict("The removed Stackarr recipe changed after review. No runtime was replaced.")
        if not available(job["source"]["port"]) or not available(job["source"]["controller_port"]):
            raise Conflict("A saved Stackarr port became occupied. No service was stopped.")
        if self.retained(saved) != job["before"] or saved["resources"] != job["resources"]:
            raise Conflict("Retained Stackarr settings changed after approval. They were preserved.")

    def recover_reinstall(self, job):
        u, source = self.updates, job["source"]
        saved = self.saved(job["removal"])
        if source != saved["source"]:
            raise DeploymentError("The reinstall belongs to another retained installation.")
        # Verify the original retained volume before changing candidate state.
        if self.resources(source) != saved["resources"]:
            raise DeploymentError("Original retained storage changed. No settings were restored.")
        with tempfile.TemporaryDirectory(prefix="reinstall-recovery-", dir=u.home) as name:
            stage = Path(name)
            if job.get("checkpoint_hash"):
                u.unpack(job, stage)
            info = self.container(job["target"])
            if info:
                if job["target"]["volume"] == source["volume"]:
                    raise DeploymentError("Another dashboard occupies the retained volume. It was not removed.")
                self.resources(job["target"], info)
            u.stop_controller(job)
            if info:
                u.stop_dashboard(job["target"])
                current = self.container(job["target"])
                if not current or current["Id"] != info["Id"] or current["State"].get("Running") or current["State"].get("ExitCode") == 137:
                    raise DeploymentError("The reinstall candidate did not stop cleanly. Its data was retained.")
                u.docker._call(["rm", info["Id"]])
            if job.get("checkpoint_hash"):
                u.restore_controller(stage)
        write(self.root / "stackarr-runtime.json", source)
        write(self.root / "compose.json", self.guard(saved["id"]))
        write(self.marker, {"format": 1, "job": saved["id"]})
        self.retained(saved)
        u.save(job, "failed-recovered", "Stackarr reinstall did not complete. Stackarr remains removed with its original account, settings and backups retained. Reopen Start Stackarr to review reinstall again; media apps stayed unchanged.")

    def finish_reinstall(self, job):
        saved = self.saved(job["removal"])
        if job["source"] != saved["source"] or self.enrollment() != saved["resources"]["enrollment"]:
            raise DeploymentError("Stackarr's retained identity changed during reinstall.")
        self.marker.unlink()
