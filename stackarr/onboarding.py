"""Resumable planning only. Drafts never activate collectors or install software."""

import json
import platform
import time
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .config import APP_IDS, CATALOG, Config, Model, Storage, validate_url
from .installer import compose_plan
from .quality import QualityProfile
from .storage import layout
from .store import Conflict


class AppChoice(Model):
    mode: Literal["install", "connect"] = "install"
    url: str = Field(default="", max_length=2048)
    browser_url: str = Field(default="", max_length=2048)
    port: int = Field(default=0, ge=0, le=65535)
    quality_profile: QualityProfile = ""

    @field_validator("url", "browser_url")
    @classmethod
    def address(cls, value):
        return validate_url(value.strip())


class SetupDraft(Model):
    step: int = Field(default=0, ge=0, le=2)
    port_mode: Literal["automatic", "defaults", "sequential", "custom"] = "automatic"
    apps: list[str] = Field(default_factory=list, max_length=len(APP_IDS))
    choices: dict[str, AppChoice] = Field(default_factory=dict)
    data_root: str = Field(default="", max_length=1024)
    folder_root: int | None = Field(default=None, ge=0)
    folder_relative: str = Field(default="", max_length=1024)

    @field_validator("apps")
    @classmethod
    def known_apps(cls, value):
        if len(set(value)) != len(value) or set(value) - set(APP_IDS):
            raise ValueError("Choose each supported application at most once")
        return value

    @field_validator("data_root")
    @classmethod
    def safe_path(cls, value):
        return Storage(data_root=value.strip()).data_root

    @model_validator(mode="after")
    def selected_choices(self):
        if set(self.choices) - set(self.apps):
            raise ValueError("Setup choices must belong to selected applications")
        if self.folder_root is None and self.folder_relative:
            raise ValueError("Choose an approved media folder first")
        if any(choice.quality_profile and (key not in {"sonarr", "radarr"} or choice.mode != "install")
               for key, choice in self.choices.items()):
            raise ValueError("Request quality choices apply only to new Sonarr and Radarr apps")
        return self

    def choice(self, key):
        # Drafts saved before mixed setup retain their original install intent.
        return self.choices.get(key, AppChoice())

    def install_apps(self):
        return [key for key in self.apps if self.choice(key).mode == "install"]


class SaveDraft(Model):
    revision: int = Field(ge=1)
    draft: SetupDraft


def initialize(store):
    with store.db() as db:
        db.execute("CREATE TABLE IF NOT EXISTS setup_draft (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER, data TEXT)")
        db.execute("INSERT OR IGNORE INTO setup_draft VALUES(1,1,?)", (SetupDraft().model_dump_json(),))


def read(store):
    with store.db() as db:
        revision, data = db.execute("SELECT revision,data FROM setup_draft WHERE id=1").fetchone()
    return {"revision": revision, "draft": SetupDraft.model_validate_json(data).model_dump()}


def save(store, body):
    with store.db() as db:
        result = db.execute(
            "UPDATE setup_draft SET revision=revision+1,data=? WHERE id=1 AND revision=?",
            (body.draft.model_dump_json(), body.revision),
        )
        if result.rowcount != 1:
            raise Conflict("Setup changed in another window. Reload to review the saved draft.")
        db.execute("INSERT INTO audit(time,event,app) VALUES(?,?,?)", (time.time(), "setup.draft-saved", "stackarr"))
    return {"revision": body.revision + 1, "draft": body.draft.model_dump()}


def connection_review(store):
    snapshot = read(store)
    draft = SetupDraft.model_validate(snapshot["draft"])
    # Validate choices before proposing any activation.
    plan(draft)
    revision, current = store.config()
    changes, notices = [], []
    for key in draft.apps:
        choice = draft.choice(key)
        if choice.mode != "connect":
            continue
        integration = current.integrations[key]
        if integration.enabled or integration.url or store.secret(key):
            notices.append(f"{CATALOG[key]['name']} already has saved settings. Review it in Apps; this wizard will preserve it.")
            continue
        changes.append({"app": key, "name": CATALOG[key]["name"], "address": choice.url,
                        "browser_address": choice.browser_url or choice.url})
    return {"revision": revision, "draft_revision": snapshot["revision"], "changes": changes, "notices": notices}


def connect_reviewed(store, review):
    with store.db() as db:
        db.execute("BEGIN IMMEDIATE")
        revision, raw = db.execute("SELECT revision,data FROM settings WHERE id=1").fetchone()
        draft_revision = db.execute("SELECT revision FROM setup_draft WHERE id=1").fetchone()[0]
        if revision != review["revision"] or draft_revision != review["draft_revision"]:
            raise Conflict("Your choices or Settings changed. Review the existing-app connections again.")
        config = Config.model_validate_json(raw)
        for change in review["changes"]:
            integration = config.integrations[change["app"]]
            integration.enabled = True
            integration.mode = "connect"
            integration.url = change["address"]
            integration.browser_url = change["browser_address"]
        if review["changes"]:
            db.execute("UPDATE settings SET revision=revision+1,data=? WHERE id=1", (config.model_dump_json(),))
            db.execute("INSERT INTO audit(time,event,app) VALUES(?,?,?)", (time.time(), "setup.connections-saved", "stackarr"))
    return {"saved": len(review["changes"]), "message": "Existing app addresses saved. Add their credentials in Apps, then test the connections. No settings inside these apps were changed."}


def readiness(draft):
    storage = layout(draft.data_root, draft.install_apps())
    missing = [CATALOG[key]["name"] for key in draft.apps
               if draft.choice(key).mode == "connect" and not draft.choice(key).url]
    return [
        {"name": "Applications", "state": "ready" if draft.apps else "needs-choice",
         "detail": f"{len(draft.apps)} selected. Unselected apps will stay hidden."},
        {"name": "Existing app addresses", "state": "needs-choice" if missing else "ready",
         "detail": "Enter an address for: " + ", ".join(missing) if missing
         else "Addresses are saved as draft choices only. Authentication and identity still need verification."},
        {"name": "Folder address", "state": "ready" if storage["valid"] else "needs-choice",
         "detail": storage["problem"] if not storage["valid"]
         else ("Address format checked only; folder access and free space still need a host check."
               if storage["required"] else "No new media installation needs a shared folder.")},
        {"name": "Installation computer", "state": "not-checked" if draft.install_apps() else "not-needed",
         "detail": "Docker, disk space, permissions, ports and startup require a paired host checker. The web server cannot certify another computer."
         if draft.install_apps() else "No new app installation is selected. Existing apps only need their addresses, credentials and connection tests."},
        {"name": "Stackarr runtime", "state": "ready",
         "detail": f"Setup is running on {platform.system()}. This may be a container, not the installation host."},
    ]


def plan(draft):
    checks = readiness(draft)
    if any(c["state"] == "needs-choice" for c in checks):
        raise ValueError("Choose an application, fill existing app addresses, and choose a full data-folder address when required.")
    config = Config()
    config.storage.data_root = draft.data_root
    for key in draft.apps:
        choice = draft.choice(key)
        config.integrations[key].mode = choice.mode
        config.integrations[key].url = choice.url if choice.mode == "connect" else ""
        config.integrations[key].browser_url = choice.browser_url if choice.mode == "connect" else ""
        config.integrations[key].port = choice.port if choice.mode == "install" else 0
        config.integrations[key].quality_profile = choice.quality_profile
        config.integrations[key].enabled = True
    config = Config.model_validate_json(config.model_dump_json())
    return {"config": json.loads(config.model_dump_json()), "plan": compose_plan(config),
            "storage": layout(draft.data_root, draft.install_apps()),
            "connections": [{"app": key, "url": draft.choice(key).url,
                             "state": "authentication-and-identity-not-verified", "managed": False}
                            for key in draft.apps if draft.choice(key).mode == "connect"],
            "checks": checks, "installation_started": False,
            "notice": "Review draft only. Host validation and the packaged installer remain required."}
