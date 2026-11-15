"""Fixed-operation local Docker installation. No browser-supplied commands or adoption."""

import asyncio
import json
import os
import platform
import re
import subprocess
import time
import uuid
from pathlib import Path

from .config import CATALOG, Config, container_port
from .docker_names import app_project, available_project
from .docker_runtime import executable
from .installer import compose_plan, preflight
from .onboarding import SetupDraft, plan, read
from .store import Conflict


class DeploymentError(ValueError):
    def __init__(self, message, retryable=False, kind=""):
        super().__init__(message)
        self.retryable = retryable
        self.kind = kind


def images():
    record = json.loads(Path(__file__).with_name("images.lock.json").read_text())
    for key, value in record["images"].items():
        repository = CATALOG[key]["image"].rsplit(":", 1)[0]
        if not re.fullmatch(re.escape(repository) + r"@sha256:[a-f0-9]{64}", value):
            raise DeploymentError("Installation image lock is invalid")
    return record["images"]


class Deployments:
    def __init__(self, store, runner=subprocess.run, auto_logins=False):
        self.store, self.runner = store, runner
        self.auto_logins = auto_logins
        with store.db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS deployments (
                id TEXT PRIMARY KEY, state TEXT, message TEXT, created REAL, updated REAL,
                payload TEXT)""")
            db.execute("CREATE TABLE IF NOT EXISTS deployment_secrets (id TEXT PRIMARY KEY, value BLOB)")
            # Do not change an idle older installation's protected database just
            # by starting a candidate controller. Create progress metadata only
            # when an approved app operation actually begins.
            steps = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='deployment_steps'").fetchone()
            if steps:
                db.execute("""UPDATE deployments SET state='interrupted',message=CASE WHEN id IN
                    (SELECT id FROM deployment_steps WHERE phase='downloading') THEN
                    'App image download interrupted. Resume the saved download; completed images remain cached and no app setup is replayed automatically.'
                    ELSE 'Installation interrupted. Review and resume; application data is preserved.' END WHERE state='running'""")
            else:
                db.execute("UPDATE deployments SET state='interrupted',message='Installation interrupted. Review and resume; application data is preserved.' WHERE state='running'")

        from .lifecycle import Lifecycle

        self.actions = Lifecycle(self)
        from .backup_policy import BackupPlans

        self.backup_plans = BackupPlans(self)
        self.backup_plans.reconcile_startup()

    def _call(self, arguments, timeout=30):
        docker = executable()
        if not docker:
            raise DeploymentError("Docker is not installed. Install Docker using its official guide, then retry.")
        try:
            result = self.runner([docker, *arguments], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=timeout,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except subprocess.TimeoutExpired:
            if "pull" in arguments:
                raise DeploymentError("The image download timed out. Check Docker and internet access, then resume; completed downloads remain cached.", retryable=True, kind="download-interrupted") from None
            raise DeploymentError("Docker did not complete this step. Check Docker Desktop and resume the saved installation.") from None
        except OSError:
            raise DeploymentError("Docker did not complete this step. Check Docker Desktop and resume the saved installation.") from None
        if result.returncode:
            from .docker_failures import classify

            kind, message, transient = classify(result.stderr, downloading="pull" in arguments)
            raise DeploymentError(message, retryable=transient, kind=kind)
        return result.stdout

    def network_capacity(self, context, project=None):
        from .docker_networks import inspect

        return inspect(lambda args: self._call(["--context", context["name"], *args], timeout=8),
                       project + "_control" if project else None)

    def require_network(self, context, project=None):
        from .docker_networks import EXHAUSTED

        result = self.network_capacity(context, project)
        if result["state"] == "exhausted" and not result.get("existing_network"):
            raise DeploymentError(EXHAUSTED, kind="network-capacity")
        return result

    def context(self):
        if os.environ.get("DOCKER_HOST") or Path("/.dockerenv").exists() or Path("/run/.containerenv").exists():
            raise DeploymentError("Installation requires the local launcher and a local Docker context.")
        if platform.machine().lower() not in ("amd64", "x86_64"):
            raise DeploymentError("This installation preview is tested only on x64 hosts.")
        context = self._call(["context", "show"]).strip()
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", context):
            raise DeploymentError("Docker context name is not supported")
        endpoint = self._call(["context", "inspect", context, "--format", "{{.Endpoints.docker.Host}}"]).strip()
        if not endpoint.startswith(("unix:///", "npipe:////./pipe/")):
            raise DeploymentError("Remote Docker contexts cannot install on this computer.")
        if self._call(["--context", context, "info", "--format", "{{.OSType}}"]).strip() != "linux":
            raise DeploymentError("Start Docker's Linux container engine, then retry.")
        return {"name": context, "endpoint": endpoint}

    def review(self):
        draft = read(self.store)
        config = Config.model_validate(plan(SetupDraft.model_validate(draft["draft"]))["config"])
        if os.name == "posix" and os.getuid() > 0 and os.getgid() > 0:
            config.storage.uid, config.storage.gid = os.getuid(), os.getgid()
        selected = [k for k, v in config.integrations.items() if v.enabled and v.mode == "install"]
        if not selected:
            raise DeploymentError("No new apps selected. Connect existing apps in Settings.")
        pinned = images()
        if set(selected) - set(pinned):
            raise DeploymentError("A selected app has no verified installation image. Update Stackarr before installing it.")
        revision, current = self.store.config()
        if any(current.integrations[k].enabled or current.integrations[k].url or self.store.secret(k) for k in selected):
            raise DeploymentError("A selected app is already configured. Existing apps will not be replaced or adopted.")
        context = self.context()
        self.require_network(context)
        checks = preflight(config)
        if any(not row["ok"] for row in checks):
            failed = ", ".join(row["check"] for row in checks if not row["ok"])
            raise DeploymentError("Resolve installation checks first: " + failed)
        compose = compose_plan(config)["compose"]
        compose["networks"] = {"control": {}}
        for key, service in compose["services"].items():
            service["image"] = pinned[key]
            service["platform"] = "linux/amd64"
            service["logging"] = {"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}}
        return {"draft_revision": draft["revision"], "config_revision": revision,
                "config": config.model_dump(), "compose": compose, "context": context,
                "apps": selected, "checks": checks, "auto_logins": self.auto_logins}

    @staticmethod
    def public(payload):
        from .managed_storage import folders
        from .quality import LABELS

        return {"apps": [{"id": key, "name": CATALOG[key]["name"],
                           "port": payload["compose"]["services"][key]["ports"][0]["published"],
                           "image": payload["compose"]["services"][key]["image"]} for key in payload["apps"]],
                "media_folder": payload["config"]["storage"]["data_root"],
                "create_folders": folders(payload["apps"]),
                "library_setup": [key for key in payload["apps"] if key in ("sonarr", "radarr")],
                "quality_setup": [{"app": key, "name": CATALOG[key]["name"], "profile": profile,
                                   "quality": LABELS[profile]} for key in payload["apps"]
                                  if (profile := payload["config"]["integrations"][key].get("quality_profile", ""))],
                "notice": "Download and start selected apps with fresh configuration volumes, a separate network and local-only ports. Your chosen media folder is shared with these apps; Plex receives read-only access. Arr API keys and a generated qBittorrent password are saved encrypted for Stackarr. When installed together, Sonarr and Radarr get separate download categories and folders. Plex and Seerr account setup remains separate. No existing app is adopted."
                + (" New Arr apps also get unique generated web logins, saved privately; existing logins are preserved." if payload.get("auto_logins") else "")}

    def enqueue(self, payload):
        from .self_update import busy

        if busy(self.store.root):
            raise Conflict("Stackarr maintenance is in progress. App changes are paused.")
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM deployments WHERE state IN ('queued','running','interrupted','failed')").fetchone():
                raise Conflict("An installation already needs attention. Resume it before starting another.")
            if db.execute("SELECT 1 FROM deployment_actions WHERE state IN ('queued','running','needs-recovery')").fetchone():
                raise Conflict("An app action is in progress. Wait for it before installing.")
            if db.execute("SELECT 1 FROM app_updates WHERE state='needs-recovery'").fetchone():
                raise Conflict("Recover the interrupted update in Apps before installing.")
            revision = db.execute("SELECT revision FROM settings WHERE id=1").fetchone()[0]
            draft_revision = db.execute("SELECT revision FROM setup_draft WHERE id=1").fetchone()[0]
            if revision != payload["config_revision"] or draft_revision != payload["draft_revision"]:
                raise Conflict("Your choices changed. Review the installation again.")
            identity = uuid.uuid4().hex
            reserved = [json.loads(raw).get("project") for (raw,) in db.execute("SELECT payload FROM deployments")]
            payload = payload | {"project": available_project(
                lambda args: self._call(["--context", payload["context"]["name"], *args]), "apps", reserved)}
            now = time.time()
            for old_id, raw in db.execute("SELECT id,payload FROM deployments WHERE state='ports-blocked'").fetchall():
                if set(json.loads(raw)["apps"]) == set(payload["apps"]):
                    db.execute("UPDATE deployments SET state='superseded',message=?,updated=? WHERE id=?",
                        ("Earlier attempt stopped before app creation; replaced by a new reviewed installation.", now, old_id))
            db.execute("INSERT INTO deployments VALUES(?,?,?,?,?,?)",
                       (identity, "queued", "Waiting to install", now, now, json.dumps(payload)))
            db.execute("INSERT INTO audit(time,event,app) VALUES(?,?,?)", (now, "deployment.approved", identity))
        return identity

    def rows(self):
        with self.store.db() as db:
            steps = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='deployment_steps'").fetchone()
            query = ("SELECT d.id,state,message,updated,payload,s.phase,s.diagnostic FROM deployments d LEFT JOIN deployment_steps s ON s.id=d.id ORDER BY created DESC LIMIT 20" if steps else
                     "SELECT id,state,message,updated,payload,NULL,NULL FROM deployments ORDER BY created DESC LIMIT 20")
            return [{"id": r[0], "state": r[1], "message": r[2], "updated": r[3], "apps": json.loads(r[4])["apps"],
                     "phase": r[5], "diagnostic": r[6], "port_recovery": bool(json.loads(r[4]).get("install_ports"))}
                    for r in db.execute(query)]

    def generated_login(self):
        """Return only our generated credential, never a connected app's secret."""
        app = self.store.config()[1].integrations["qbittorrent"]
        current = self.store.secret("qbittorrent")
        with self.store.db() as db:
            rows = db.execute("SELECT d.payload,s.value FROM deployments d JOIN deployment_secrets s ON s.id=d.id WHERE d.state='needs-setup'").fetchall()
        for raw, encrypted in rows:
            payload = json.loads(raw)
            if "qbittorrent" not in payload["apps"]:
                continue
            port = payload["compose"]["services"]["qbittorrent"]["ports"][0]["published"]
            saved = json.loads(self.store.cipher.decrypt(encrypted)).get("qbittorrent")
            if app.enabled and app.url == f"http://127.0.0.1:{port}" and saved and current == saved:
                return saved
        raise DeploymentError("No unchanged Stackarr-generated qBittorrent login is available. Use the credentials you set for this application.")

    def resume(self, identity):
        with self.store.db() as db:
            steps = db.execute("SELECT 1 FROM sqlite_master WHERE name='deployment_steps'").fetchone()
            row = db.execute("SELECT state,payload FROM deployments WHERE id=?", (identity,)).fetchone()
            diagnostic = db.execute("SELECT diagnostic FROM deployment_steps WHERE id=?", (identity,)).fetchone() if steps else None
        if row and row[0] in {"failed", "interrupted"} and diagnostic and diagnostic[0] == "startup-port-conflict" and not json.loads(row[1]).get("install_ports"):
            from .install_ports import InstallPorts

            InstallPorts(self).resume_original(identity)
            return
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM deployment_actions WHERE state IN ('queued','running','needs-recovery')").fetchone():
                raise Conflict("An app action is in progress. Wait for it before resuming.")
            if db.execute("SELECT 1 FROM app_updates WHERE state='needs-recovery'").fetchone():
                raise Conflict("Recover the interrupted update in Apps before resuming.")
            row = db.execute("SELECT state,payload FROM deployments WHERE id=?", (identity,)).fetchone()
            if not row or row[0] not in ("failed", "interrupted"):
                raise Conflict("Only a failed or interrupted installation can resume.")
            payload = json.loads(row[1])
            revision, raw = db.execute("SELECT revision,data FROM settings WHERE id=1").fetchone()
            if revision != payload["config_revision"]:
                current = Config.model_validate_json(raw)
                for key in payload["apps"]:
                    if current.integrations[key].enabled or current.integrations[key].url or db.execute("SELECT 1 FROM secrets WHERE name=?", (key,)).fetchone():
                        raise Conflict("An app in this installation now has saved connection settings. Those settings are preserved; resolve the conflict before resuming.")
                # The reviewed images, paths and ports remain immutable. Unrelated
                # dashboard/preferences changes do not permanently strand an install.
                payload["config_revision"] = revision
                db.execute("UPDATE deployments SET payload=? WHERE id=?", (json.dumps(payload), identity))
            db.execute("UPDATE deployments SET state='queued',message='Waiting to resume',updated=? WHERE id=?", (time.time(), identity))
            db.execute("INSERT INTO audit(time,event,app) VALUES(?,?,?)", (time.time(), "deployment.resumed", identity))

    def _message(self, identity, message):
        with self.store.db() as db:
            db.execute("UPDATE deployments SET message=?,updated=? WHERE id=?", (message, time.time(), identity))

    def _step(self, identity, phase, diagnostic=""):
        with self.store.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS deployment_steps (id TEXT PRIMARY KEY, phase TEXT, diagnostic TEXT)")
            db.execute("INSERT OR REPLACE INTO deployment_steps VALUES(?,?,?)", (identity, phase, diagnostic))

    def _pull(self, identity, base, services):
        if not services:
            return
        # Only downloading immutable images is retried. Never replay app writes.
        for attempt in range(3):
            try:
                self._call([*base, "pull", "--policy", "missing", *services], timeout=300)
                return
            except DeploymentError as exc:
                if not exc.retryable or attempt == 2:
                    if exc.kind in {"download-storage", "download-unavailable"}:
                        raise
                    raise DeploymentError("Application image download failed or was interrupted. Check Docker and internet access, then resume the saved download. Completed images remain cached; existing app data is retained.", kind="download-interrupted") from None
                self._message(identity, f"Image registry temporarily unavailable. Retrying download ({attempt + 2}/3).")
                time.sleep(5 * (attempt + 1))

    def _verify_images(self, payload):
        from .bundled_images import verify

        for service in payload["compose"]["services"].values():
            verify(lambda args: self._call(["--context", payload["context"]["name"], *args]), service["image"])
            try:
                info = json.loads(self._call(["--context", payload["context"]["name"], "image", "inspect", "--format",
                    '{"id":{{json .Id}},"digests":{{json .RepoDigests}},"os":{{json .Os}},"arch":{{json .Architecture}}}', service["image"]]))
                valid = (re.fullmatch(r"sha256:[a-f0-9]{64}", info["id"]) and service["image"] in info["digests"]
                         and info["os"] == "linux" and info["arch"] == "amd64")
                if not valid:
                    raise ValueError("Unverified image")
            except Exception:
                raise DeploymentError("A reviewed app image is incomplete or does not match its pinned digest/platform. Resume the download before starting apps; existing data is retained.", kind="download-verification") from None

    def owned_container(self, identity, payload, key):
        project = app_project(identity, payload)
        name = project + "-" + key + "-1"
        info = json.loads(self._call(["--context", payload["context"]["name"], "inspect", name]))[0]
        labels = info["Config"]["Labels"]
        if labels.get("com.docker.compose.project") != project or labels.get("com.docker.compose.service") != key:
            raise DeploymentError("App container ownership could not be verified")
        if info["Config"]["Image"] != payload["compose"]["services"][key]["image"]:
            raise DeploymentError("App image changed; credential handoff stopped")
        config_mount = next((m for m in info["Mounts"] if m["Destination"] == CATALOG[key]["config"]), None)
        if not config_mount or config_mount.get("Name") != project + "_" + key + "-config":
            raise DeploymentError("App configuration volume ownership could not be verified")
        expected_port = str(container_port(key, Config.model_validate(payload["config"]).integrations[key])) + "/tcp"
        bindings = info["NetworkSettings"]["Ports"].get(expected_port, [])
        reviewed_port = payload["compose"]["services"][key]["ports"][0]["published"]
        if not bindings or any(b["HostIp"] != "127.0.0.1" or b["HostPort"] != reviewed_port for b in bindings):
            raise DeploymentError("App port changed; credential handoff stopped")
        return name

    def execute(self, identity, payload):
        if self.context() != payload["context"]:
            raise DeploymentError("Docker context changed. Select the reviewed local context before resuming.")
        if self.store.config()[0] != payload["config_revision"]:
            raise DeploymentError("Settings changed. This deployment is preserved; review its connections before continuing.")
        root = self.store.root / "deployments"
        directory = root / identity
        if not re.fullmatch(r"[a-f0-9]{32}", identity):
            raise DeploymentError("Invalid deployment identity")
        for path in (root, directory):
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise DeploymentError("Deployment directories must not be filesystem links")
        directory.mkdir(parents=True, exist_ok=True)
        filename = directory / "compose.json"
        if payload.get("install_ports"):
            from .install_ports import InstallPorts

            InstallPorts(self).reconcile(identity, payload, filename)
        content = json.dumps(payload["compose"], sort_keys=True)
        if filename.exists():
            if filename.is_symlink() or filename.read_text(encoding="utf-8") != content:
                raise DeploymentError("Installation files changed. Inspect them before resuming.")
        else:
            with filename.open("x", encoding="utf-8") as output:
                output.write(content)
        project = app_project(identity, payload)
        base = ["--context", payload["context"]["name"], "compose", "--project-name", project, "-f", str(filename)]
        self._call([*base, "config", "--quiet"])
        self.require_network(payload["context"], project)
        self._step(identity, "downloading")
        self._message(identity, "Downloading the reviewed application images")
        from .bundled_images import verify

        registry_services = []
        for key, service in payload["compose"]["services"].items():
            if not verify(lambda args: self._call(["--context", payload["context"]["name"], *args]), service["image"]):
                registry_services.append(key)
        self._pull(identity, base, registry_services)
        self._verify_images(payload)
        # Never create folders, volumes or containers when a port was taken during an image download.
        # A resumed partial deployment already owns its ports and follows the existing ownership checks.
        if not self._call([*base, "ps", "-a", "-q"]).strip():
            from .onboarding import AppChoice, SetupDraft
            from .ports import ensure

            ensure(SetupDraft(apps=payload["apps"], choices={key: AppChoice(port=int(
                payload["compose"]["services"][key]["ports"][0]["published"])) for key in payload["apps"]}))
        self._message(identity, "Starting your applications; existing deployments remain untouched")
        self._step(identity, "starting")
        from .managed_storage import prepare

        try:
            prepare(payload["config"]["storage"]["data_root"], payload["apps"])
        except (OSError, ValueError):
            raise DeploymentError("The reviewed media folders could not be prepared. Check the folder is writable and contains no filesystem links or conflicting files, then resume. Existing files are preserved.") from None
        try:
            if payload.get("install_ports"):
                InstallPorts(self).start(identity, payload, base)
            else:
                self._call([*base, "up", "-d", "--pull", "never", "--wait", "--wait-timeout", "180"], timeout=240)
        except DeploymentError as exc:
            if exc.kind in {"network-capacity", "startup-port-conflict"}:
                raise
            raise DeploymentError("Application startup failed. Check Docker, available ports and media folder access, then resume; application data is preserved.") from None
        self._message(identity, "Connecting newly installed apps and saving their credentials securely")
        self._step(identity, "configuring")
        from .seerr_storage import prepare as prepare_seerr_storage

        prepare_seerr_storage(self, identity, payload)
        from .bootstrap import credentials

        saved = credentials(self, identity, payload)
        from .bootstrap import download_categories, libraries, quality_profiles

        quality_profiles(payload, saved)
        libraries(payload, saved)
        download_categories(payload, saved)
        from .arr_logins import prepare as prepare_logins

        if self.auto_logins:
            prepare_logins(self, identity, payload, saved)
        # Activation and completion share one transaction, so restart cannot duplicate them.
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            revision, raw = db.execute("SELECT revision,data FROM settings WHERE id=1").fetchone()
            if revision != payload["config_revision"]:
                raise DeploymentError("Apps started, but Settings changed. Their data is preserved; connect them after reviewing Settings.")
            config = Config.model_validate_json(raw).model_dump()
            if any(key in payload["apps"] for key in ("plex", "sonarr", "radarr", "qbittorrent")) and not config["storage"]["data_root"]:
                config["storage"] = payload["config"]["storage"]
            for key in payload["apps"]:
                port = payload["compose"]["services"][key]["ports"][0]["published"]
                config["integrations"][key].update(enabled=True, mode="connect", url=f"http://127.0.0.1:{port}",
                                                     port=int(port),
                                                     quality_profile=payload["config"]["integrations"][key].get("quality_profile", ""),
                                                     browser_url=f"http://localhost:{port}/web" if key == "plex" else f"http://127.0.0.1:{port}",
                                                     peer_url=f"http://{key}:{payload['compose']['services'][key]['ports'][0]['target']}")
            config = Config.model_validate(config)
            db.execute("UPDATE settings SET revision=revision+1,data=? WHERE id=1", (config.model_dump_json(),))
            for key, secret in saved.items():
                db.execute("INSERT OR REPLACE INTO secrets VALUES(?,?)", (key, self.store.cipher.encrypt(json.dumps(secret).encode())))
            db.execute("UPDATE deployments SET state='needs-setup',message=?,updated=? WHERE id=?",
                       ("Apps started and supported credentials saved. Review app connections in Apps; finish Plex/Seerr account setup where selected.", time.time(), identity))
            db.execute("INSERT INTO audit(time,event,app) VALUES(?,?,?)", (time.time(), "deployment.started", identity))
            db.execute("UPDATE deployment_steps SET phase='complete',diagnostic='' WHERE id=?", (identity,))

    async def run_one(self):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id,payload FROM deployments WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
            if not row:
                return False
            identity, raw = row
            db.execute("UPDATE deployments SET state='running',updated=? WHERE id=?", (time.time(), identity))
        try:
            self._step(identity, "preparing")
            await asyncio.to_thread(self.execute, identity, json.loads(raw))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            from .bootstrap import BootstrapError
            from .ports import PortsUnavailable

            message = str(exc) if isinstance(exc, (DeploymentError, BootstrapError, PortsUnavailable)) else "Installation could not finish. Your app data is preserved. Check Docker and resume."
            recovering_ports = isinstance(exc, PortsUnavailable) and bool(json.loads(raw).get("install_ports"))
            if recovering_ports:
                message = "An app port became busy during recovery. Choose Review available ports for this same installation, or free its original port and resume. Existing settings and media are retained."
            state = "ports-blocked" if isinstance(exc, PortsUnavailable) and not recovering_ports else "failed"
            with self.store.db() as db:
                db.execute("UPDATE deployments SET state=?,message=?,updated=? WHERE id=?", (state, message, time.time(), identity))
                db.execute("UPDATE deployment_steps SET diagnostic=? WHERE id=?", ("startup-port-conflict" if recovering_ports else getattr(exc, "kind", ""), identity))
                db.execute("INSERT INTO audit(time,event,app) VALUES(?,?,?)", (time.time(), "deployment.failed", identity))
        return True

    async def work(self):
        while True:
            from .self_update import busy

            if busy(self.store.root):
                await asyncio.sleep(.5)
                continue
            if not await self.run_one() and not await self.actions.run_one():
                try:
                    await asyncio.to_thread(self.backup_plans.tick)
                except Exception:
                    # A disconnected destination cannot stop the controller's operation worker.
                    self.store.audit("app-backup.scheduler-failed")
                await asyncio.sleep(.5)
