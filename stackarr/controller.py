"""Host-owned installation boundary. No browser-supplied Compose or commands.

The private transport exposes only reviewed operations; credential handoff is
still separate from installation.
"""

import json
import os
import secrets
import threading
import time
from typing import Annotated

from pydantic import Field, StrictInt, field_validator, model_validator

from . import onboarding
from .config import APP_IDS, Model
from .deployment import Deployments
from .docker_names import app_project
from .folder_browser import FolderBrowser
from .ports import check, ensure, suggestions
from .quality import QualityProfile
from .store import Conflict


class PortIntent(Model):
    """Only app identities, ports and a host-approved folder reference cross over."""

    apps: list[str] = Field(min_length=1, max_length=len(APP_IDS))
    ports: dict[str, Annotated[StrictInt, Field(ge=1, le=65535)]]

    @field_validator("apps")
    @classmethod
    def known_apps(cls, value):
        if len(value) != len(set(value)) or set(value) - set(APP_IDS):
            raise ValueError("Select each supported app once")
        return value

    @model_validator(mode="after")
    def complete_ports(self):
        if set(self.ports) != set(self.apps):
            raise ValueError("Supply exactly one port for each selected app")
        return self


class InstallIntent(PortIntent):
    folder: Annotated[StrictInt, Field(ge=0)] | None = None
    relative: str = Field(default="", max_length=1024)
    quality_profiles: dict[str, QualityProfile] = Field(default_factory=dict)

    @model_validator(mode="after")
    def installation_choices(self):
        if len(set(self.ports.values())) != len(self.ports):
            raise ValueError("Each app needs a different port")
        if self.folder is None and self.relative:
            raise ValueError("Choose an approved folder first")
        if set(self.quality_profiles) - (set(self.apps) & {"sonarr", "radarr"}):
            raise ValueError("Choose request quality only for selected Sonarr and Radarr apps")
        return self


class InstallationController:
    """One dashboard per host controller; its state directory is host-owned.

    Review references are internal, single-use capabilities, never user-facing
    setup codes. The authenticated transport must not expose them to logs.
    """

    def __init__(self, store, roots, dashboard_port, deployments=None, clock=time.monotonic,
                 controller_port=28010, folder_chooser=None):
        if type(dashboard_port) is not int or not 1 <= dashboard_port <= 65535:
            raise ValueError("A valid dashboard port is required")
        # References are resolved on the host, not using dashboard-provided paths.
        if any(str(FolderBrowser.host(r["host_path"])) != str(FolderBrowser.host(r["path"])) for r in roots):
            raise ValueError("Controller folders must reference paths on this host")
        from .media_folders import approved, choose

        self.browser = FolderBrowser(approved(store, roots))
        self.folder_chooser = folder_chooser or choose
        self.picker_available = folder_chooser is not None or os.name == "nt"
        self.picker_lock = threading.Lock()
        self.reserved_ports = {dashboard_port, controller_port}
        self.store, self.dashboard_port, self.clock = store, dashboard_port, clock
        onboarding.initialize(store)
        self.deployments = deployments or Deployments(store, auto_logins=True)
        self.lock = threading.Lock()
        self.pending = None
        self.managed_reviews = {}
        self.account_reviews = {}
        from .native_import import NativeImporter

        self.native_importer = NativeImporter(enabled=True)

    def folders(self, root=None, relative=""):
        if root is None and relative:
            raise ValueError("Choose an approved media folder first")
        return self.browser.browse(root, relative)

    def media_folder(self):
        from .media_folders import grant

        if not self.picker_available:
            raise ValueError("Choose a folder already shared with this installation computer.")
        if not self.picker_lock.acquire(blocking=False):
            raise Conflict("A folder chooser is already open. Finish that choice first.")
        try:
            path = self.folder_chooser()
            if not path:
                return {"cancelled": True}
            with self.lock:
                roots, index = grant(self.store, path)
                self.browser = FolderBrowser(roots)
                selected = self.browser.browse(index)
            return {"cancelled": False, "path": selected["host_path"], "root": index, "relative": ""}
        finally:
            self.picker_lock.release()

    def ports(self, intent: PortIntent, suggest=False):
        intent = PortIntent.model_validate(intent)
        draft = onboarding.SetupDraft(
            apps=intent.apps, port_mode="custom",
            choices={key: onboarding.AppChoice(port=intent.ports[key]) for key in intent.apps},
        )
        return {"suggestions": suggestions(draft, self.reserved_ports)} if suggest else {"ports": check(draft, self.reserved_ports)}

    def review(self, intent: InstallIntent):
        # Validate even when called by a non-HTTP transport.
        intent = InstallIntent.model_validate(intent)
        if self.reserved_ports & set(intent.ports.values()):
            raise ValueError("An app cannot use Stackarr's dashboard or private setup port")
        media_apps = {"plex", "sonarr", "radarr", "qbittorrent"}
        if set(intent.apps) & media_apps and intent.folder is None:
            raise ValueError("Choose an approved media folder")
        path = ""
        if intent.folder is not None:
            path = str(self.browser.resolve(intent.folder, intent.relative))
        with self.lock:
            # A new review replaces the previous approval, including failed reviews.
            self.pending = None
            if any(row["state"] in {"queued", "running", "failed", "interrupted"}
                   for row in self.deployments.rows()):
                raise Conflict("An installation needs attention. Resume it before reviewing another.")
            draft = onboarding.SetupDraft(
                apps=intent.apps, data_root=path, port_mode="custom",
                choices={key: onboarding.AppChoice(port=intent.ports[key],
                    quality_profile=intent.quality_profiles.get(key, "")) for key in intent.apps},
            )
            onboarding.save(self.store, onboarding.SaveDraft(
                revision=onboarding.read(self.store)["revision"], draft=draft,
            ))
            payload = self.deployments.review()
            reference = secrets.token_urlsafe(32)
            self.pending = (reference, self.clock() + 300, payload, intent)
            return {"review_reference": reference, "expires_in": 300,
                    "plan": self.deployments.public(payload)}

    def install(self, reference):
        with self.lock:
            pending = self.pending
            if (not isinstance(reference, str) or not reference.isascii() or not pending
                    or not secrets.compare_digest(reference, pending[0])):
                raise Conflict("Review this installation before starting it")
            self.pending = None
            if self.clock() >= pending[1]:
                raise Conflict("The installation review expired. Review again")
            payload, intent = pending[2:]
            ensure(onboarding.SetupDraft(apps=intent.apps, choices={key: onboarding.AppChoice(port=intent.ports[key])
                   for key in intent.apps}), self.reserved_ports)
            # Recheck folder boundaries after the review; no browsing of new roots.
            if intent.folder is not None:
                path = str(self.browser.resolve(intent.folder, intent.relative))
                if path != payload["config"]["storage"]["data_root"]:
                    raise Conflict("The media folder changed. Review again")
            return {"id": self.deployments.enqueue(payload)}

    def status(self):
        # Return local browser links only after the owned installation completed.
        # Stored Compose and credentials never cross this boundary.
        operations = self.deployments.rows()
        with self.store.db() as db:
            for row in operations:
                saved = db.execute("SELECT payload FROM deployments WHERE id=?", (row["id"],)).fetchone()
                if not saved:
                    continue
                payload = json.loads(saved[0])
                if row.get("port_recovery"):
                    row["ports"] = {key: int(payload["compose"]["services"][key]["ports"][0]["published"]) for key in payload["apps"]}
                if row["state"] != "needs-setup":
                    continue
                row["links"] = [{"app": key, "url": "http://localhost:" + str(
                    payload["compose"]["services"][key]["ports"][0]["published"]) + ("/web" if key == "plex" else "")}
                    for key in row["apps"]]
        from .companions import APPS, Companions

        companions = Companions(self.deployments)
        logins = sorted({key for row in operations for key, value in companions.state(row["id"])["apps"].items()
                         if key in APPS and value.get("complete")})
        return {"operations": operations, "folder_browser": bool(self.browser.roots), "folder_picker": self.picker_available,
                "actions": self.deployments.actions.rows(), "companion_login_apps": logins}

    def installation_check(self, identity):
        from .deployment_check import check

        with self.lock:
            return check(self.deployments, identity)

    def managed_review(self, identity, action, app=None, backup=None, update=None, operation=None):
        from .app_backups import AppBackups

        with self.lock:
            if (self.deployments.actions.busy() and action not in {"update-recover", "repair-recover"}) or any(row["state"] in {"queued", "running"} for row in self.deployments.rows()):
                raise Conflict("Wait for the current app operation to finish.")
            if operation is not None and action != "repair-recover":
                raise ValueError("A saved maintenance operation is only used for recovery")
            if action == "install-ports":
                from .install_ports import InstallPorts

                if any(value is not None for value in (app, backup, update, operation)):
                    raise ValueError("Choose only a saved installation for port recovery")
                service = InstallPorts(self.deployments)
                review = service.review(identity, self.reserved_ports)
                public = service.public(review)
            elif action == "companions":
                from .companions import Companions

                if app is not None or backup is not None or update is not None:
                    raise ValueError("Choose a companion installation only")
                service = Companions(self.deployments)
                review = service.review(identity)
                public = service.public(review)
            elif action in {"update", "rollback", "update-recover"}:
                from .updates import Updates

                if backup is not None:
                    raise ValueError("Choose an update, not a configuration restore")
                service = Updates(self.deployments)
                review = service.review(identity, app, action, update)
                public = service.public(review)
            elif action in {"backup", "restore"}:
                if update is not None:
                    raise ValueError("Choose an app backup")
                if app is not None or (action == "restore") != bool(backup):
                    raise ValueError("Choose a saved backup for restore")
                service = AppBackups(self.deployments)
                review = service.review(identity, backup)
                public = service.public(review)
            else:
                if backup is not None or update is not None:
                    raise ValueError("An app action cannot include a backup")
                review = self.deployments.actions.review(identity, app, action, operation)
                public = self.deployments.actions.public(review)
            self.managed_reviews = {key: value for key, value in self.managed_reviews.items() if value[0] > self.clock()}
            if len(self.managed_reviews) >= 100:
                raise Conflict("Too many pending reviews. Wait before trying again.")
            reference = secrets.token_urlsafe(32)
            self.managed_reviews[reference] = (self.clock() + 300, review)
            return public | {"review_reference": reference, "expires_in": 300}

    def managed_apply(self, reference):
        with self.lock:
            pending = self.managed_reviews.pop(reference, None)
            if not pending or pending[0] <= self.clock():
                raise Conflict("Review this operation again before applying it.")
            if pending[1]["action"] == "backup-policy":
                if self.deployments.actions.busy() or any(row["state"] in {"queued", "running"} for row in self.deployments.rows()):
                    raise Conflict("Wait for the current app operation, then review the backup plan again.")
                return self.deployments.backup_plans.configure(pending[1])
            if pending[1]["action"] == "install-ports":
                from .install_ports import InstallPorts

                return InstallPorts(self.deployments).approve(pending[1])
            return {"id": self.deployments.actions.enqueue(pending[1])}

    def backup_policy_review(self, value):
        with self.lock:
            if self.deployments.actions.busy() or any(row["state"] in {"queued", "running"} for row in self.deployments.rows()):
                raise Conflict("Wait for the current app operation to finish.")
            review = self.deployments.backup_plans.review(value)
            reference = secrets.token_urlsafe(32)
            self.managed_reviews = {key: item for key, item in self.managed_reviews.items() if item[0] > self.clock()}
            if len(self.managed_reviews) >= 100:
                raise Conflict("Too many pending reviews. Wait before trying again.")
            self.managed_reviews[reference] = (self.clock() + 300, review)
            return {key: value for key, value in review.items() if key not in {"policy", "revision"}} | {"review_reference": reference, "expires_in": 300}

    def backup_key(self):
        _, policy = self.deployments.backup_plans.read()
        return {"format": 1, "namespace": policy["namespace"],
                "key": (self.store.root / "secrets.key").read_text().strip(),
                "notice": "Keep this recovery key separately and privately. It unlocks app backups and whole-host recovery files. Media files are excluded."}

    def stackarr_update_review(self, action, identity):
        from .self_update import SelfUpdates

        with self.lock:
            if action != "recover" and (self.deployments.actions.busy() or any(r["state"] in {"queued", "running"} for r in self.deployments.rows())):
                raise Conflict("Wait for app maintenance to finish before updating Stackarr.")
            review = SelfUpdates.controller(self).review(action, identity)
            self.managed_reviews = {key: value for key, value in self.managed_reviews.items() if value[0] > self.clock()}
            if len(self.managed_reviews) >= 100:
                raise Conflict("Too many pending reviews. Wait before trying again.")
            reference = secrets.token_urlsafe(32)
            self.managed_reviews[reference] = (self.clock() + 300, review)
            return SelfUpdates.public(review) | {"review_reference": reference}

    def stackarr_update_apply(self, reference):
        from .self_update import SelfUpdates

        with self.lock:
            pending = self.managed_reviews.pop(reference, None)
            if not pending or pending[0] <= self.clock():
                raise Conflict("Review the Stackarr update again before applying it.")
            if pending[1]["action"] != "recover" and (self.deployments.actions.busy() or any(r["state"] in {"queued", "running"} for r in self.deployments.rows())):
                raise Conflict("Wait for app maintenance to finish.")
            return SelfUpdates.controller(self).approve(pending[1])

    def host_backup_review(self):
        from .host_recovery import HostBackups

        with self.lock:
            if self.deployments.actions.busy():
                raise Conflict("Wait for the current app operation to finish.")
            service = HostBackups(self.deployments, self.dashboard_port)
            review = service.review()
            self.managed_reviews = {key: item for key, item in self.managed_reviews.items() if item[0] > self.clock()}
            if len(self.managed_reviews) >= 100:
                raise Conflict("Too many pending reviews. Wait before trying again.")
            reference = secrets.token_urlsafe(32)
            self.managed_reviews[reference] = (self.clock() + 300, review)
            return service.public(review) | {"review_reference": reference, "expires_in": 300}

    def backups(self):
        from .app_backups import AppBackups

        return {"backups": AppBackups(self.deployments).rows()}

    def updates(self):
        from .updates import Updates

        return Updates(self.deployments).listing()

    def companion_connections(self, identity):
        from .companions import Companions

        with self.lock:
            if self.deployments.actions.busy():
                raise Conflict("Wait for companion setup to finish.")
            return Companions(self.deployments).connections(identity)

    def companion_login(self, identity, key):
        from .companions import Companions

        with self.lock:
            if self.deployments.actions.busy():
                raise Conflict("Wait for companion setup to finish.")
            return Companions(self.deployments).login(identity, key)

    def accounts_review(self, identity):
        import asyncio

        from .account_setup import Accounts

        with self.lock:
            if self.deployments.actions.busy() or any(row["state"] in {"queued", "running"} for row in self.deployments.rows()):
                raise Conflict("Wait for installation to finish, then connect Plex.")
            plan = asyncio.run(Accounts(self.deployments).review(identity))
            self.account_reviews = {key: value for key, value in self.account_reviews.items() if value[0] > self.clock()}
            if len(self.account_reviews) >= 50:
                raise Conflict("Wait a moment before reviewing account setup again.")
            reference = secrets.token_urlsafe(32)
            self.account_reviews[reference] = (self.clock() + 300, plan)
            return Accounts.public(plan) | {"review_reference": reference, "expires_in": 300}

    def accounts_apply(self, reference):
        import asyncio

        from .account_setup import Accounts
        from .finish_setup import finish

        with self.lock:
            pending = self.account_reviews.pop(reference, None)
            if not pending or pending[0] <= self.clock():
                raise Conflict("Review account setup again before continuing.")
            if self.deployments.actions.busy() or any(row["state"] in {"queued", "running"} for row in self.deployments.rows()):
                raise Conflict("Wait for the current app operation, then review account setup again.")
            async def apply():
                result = await Accounts(self.deployments).apply(pending[1])
                result["connections"] = await finish(self.deployments, pending[1]["id"])
                return result
            return asyncio.run(apply())

    def plex_connection(self, identity):
        """Private credential candidate; never included in public installation status."""
        return self.account_connection(identity, "plex")

    def seerr_connection(self, identity):
        """Private candidate only after owned Seerr account setup is complete."""
        return self.account_connection(identity, "seerr")

    def account_connection(self, identity, key):
        from .deployment_check import load_receipt
        from .finish_setup import read_candidate

        if key not in {"plex", "seerr"}:
            raise ValueError("Choose a supported owned account app")
        with self.lock:
            if any(row["state"] in {"queued", "running"} for row in self.deployments.rows()) or self.deployments.actions.busy():
                raise Conflict("Wait for the app operation to finish before connecting this app.")
            payload = load_receipt(self.deployments, identity)
            if key not in payload["apps"] or self.deployments.context() != payload["context"]:
                raise ValueError("App ownership could not be verified")
            integration = self.store.config()[1].integrations[key]
            candidate = read_candidate(self.deployments, identity, payload, key, integration)
            return {"id": identity, "port": int(payload["compose"]["services"][key]["ports"][0]["published"]),
                    "credential": candidate}

    def resume(self, identity):
        with self.lock:
            self.deployments.resume(identity)
        return {"id": identity}

    def app_connections(self, identity):
        """Return checkpointed credentials only for unchanged, newly owned core apps."""
        from .deployment_check import differences, inspect_container, load_receipt

        with self.lock:
            if any(row["state"] in {"queued", "running"} for row in self.deployments.rows()) or self.deployments.actions.busy():
                raise Conflict("Wait for the app operation to finish before connecting apps.")
            payload = load_receipt(self.deployments, identity)
            with self.store.db() as db:
                row = db.execute("SELECT value FROM deployment_secrets WHERE id=?", (identity,)).fetchone()
            saved = json.loads(self.store.cipher.decrypt(row[0])) if row else {}
            config = self.store.config()[1]
            result = {}
            for key in payload["apps"]:
                if key not in {"sonarr", "radarr", "prowlarr", "qbittorrent"}:
                    continue
                service = payload["compose"]["services"][key]
                port = int(service["ports"][0]["published"])
                integration = config.integrations[key]
                if (not integration.enabled or integration.url != f"http://127.0.0.1:{port}"
                        or not saved.get(key) or self.store.secret(key) != saved[key]):
                    raise ValueError("Installed app credentials changed; preserve the saved settings.")
                info = inspect_container(self.deployments, identity, payload, key)
                runtime = info.get("State", {})
                if (differences(info, app_project(identity, payload), key, service)
                        or not runtime.get("Running") or runtime.get("Paused") or runtime.get("Restarting")):
                    raise ValueError("Installed app identity or running state changed.")
                result[key] = {"port": port, "credential": saved[key]}
            return {"id": identity, "apps": result}

    def arr_logins(self, identity):
        from .arr_logins import prepare
        from .deployment_check import load_receipt

        # The private credential operation already verifies receipts, context and unchanged keys.
        credentials = self.app_connections(identity)
        with self.lock:
            if any(row["state"] in {"queued", "running"} for row in self.deployments.rows()) or self.deployments.actions.busy():
                raise Conflict("Wait for the app operation before setting up logins.")
            payload = load_receipt(self.deployments, identity)
            return prepare(self.deployments, identity, payload,
                           {key: value["credential"] for key, value in credentials["apps"].items()})

    def arr_login(self, identity, key):
        from .arr_logins import ARR, read
        from .deployment_check import load_receipt

        with self.lock:
            if key not in ARR or self.deployments.actions.busy() or any(
                row["state"] in {"queued", "running"} for row in self.deployments.rows()
            ):
                raise ValueError("Choose an owned Arr app after installation finishes.")
            payload = load_receipt(self.deployments, identity)
            if key not in payload["apps"]:
                raise ValueError("Choose an app in this installation.")
            port = int(payload["compose"]["services"][key]["ports"][0]["published"])
            app, credential = self.store.config()[1].integrations[key], self.store.secret(key)
            if not app.enabled or app.url != f"http://127.0.0.1:{port}":
                raise ValueError("The saved app connection changed.")
            api_key = credential.get("api_key")
            return {"id": identity, "app": key, "port": port, "api_key": api_key,
                    "login": read(self.deployments, identity, payload, key, api_key)}
