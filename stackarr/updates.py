"""Reviewed immutable-image updates coupled to encrypted configuration snapshots.

Only fixed catalog images and exact owned services are eligible. No pruning,
archive uploads, user-supplied images, or media-file operations are exposed.
"""

import asyncio
import copy
import json
import os
import re
import tempfile
import time
import uuid
from pathlib import Path

import httpx

from .app_backups import AppBackups, compatibility
from .config import CATALOG
from .deployment import DeploymentError
from .deployment_check import differences, inspect_container, load_receipt
from .docker_names import app_project
from .integrations import bounded_response, collect
from .store import Conflict

LABEL = "io.stackarr.update"
PHASES = {
    "preparing": "Preparing update", "backup-verified": "Configuration backup verified",
    "applying-candidate": "Starting candidate image", "applying-candidate-health": "Checking candidate health",
    "committing-receipt": "Saving verified installation", "updated-and-healthy": "Updated and healthy",
    "restoring-previous": "Restoring previous image and settings", "restoring-previous-health": "Checking recovered app",
    "previous-image-and-data-restored": "Previous image and settings restored", "original-app-preserved": "Original app preserved",
    "rollback-safety-saved": "Current settings safety copy saved", "restoring-current": "Recovering current image and settings",
    "restoring-current-health": "Checking current app recovery", "rollback-failed-current-restored": "Current app recovered after rollback failed",
    "recovery-review-required": "Recovery review required",
}


def initialize(store):
    with store.db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS app_updates (
            id TEXT PRIMARY KEY, deployment TEXT, app TEXT, state TEXT, phase TEXT,
            created REAL, updated REAL, value BLOB)""")


def catalog():
    record = json.loads(Path(__file__).with_name("updates.lock.json").read_text())
    if record["schema"] != 1 or record["platform"] != "linux/amd64":
        raise DeploymentError("Update catalog is incompatible. Keep the current apps.")
    for key, value in record["apps"].items():
        repository = CATALOG[key]["image"].rsplit(":", 1)[0]
        if not re.fullmatch(re.escape(repository) + r"@sha256:[a-f0-9]{64}", value["image"]):
            raise DeploymentError("Update catalog contains an unapproved image.")
    return record


def app_version(value):
    return value.lstrip("v").split("-ls", 1)[0].split("_", 1)[0]


def version_order(value):
    base = re.match(r"\d+(?:\.\d+)*", app_version(value))
    if not base:
        raise DeploymentError("The image version format is unsupported.")
    build = re.search(r"-ls(\d+)$", value)
    patch = re.search(r"-stackarr\.(\d+)$", value)
    return tuple(map(int, base[0].split("."))), int(build[1]) if build else 0, int(patch[1]) if patch else 0


async def response_version(key, base, secret):
    if key in {"tautulli", "kuma", "cleanuparr"}:
        from .companion_maintenance import version

        return await version(key, base, secret)
    headers = {"Accept": "application/json", "X-Plex-Token" if key == "plex" else "X-Api-Key": secret.get("api_key", "")}
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=5, headers=headers) as client:
        if key == "qbittorrent":
            response, _ = await bounded_response(client, "POST", base + "/api/v2/auth/login", data={"username": secret.get("username"), "password": secret.get("password")}, headers={"Referer": base})
            response.raise_for_status()
        path = {"plex": "/identity", "seerr": "/api/v1/status", "qbittorrent": "/api/v2/app/version"}.get(key, "/api/v1/system/status" if key == "prowlarr" else "/api/v3/system/status")
        response, body = await bounded_response(client, "GET", base + path)
        response.raise_for_status()
        if key == "qbittorrent":
            return body.decode().strip()
        data = json.loads(body)
        return (data["MediaContainer"] if key == "plex" else data)["version"]


async def protected_state(payload, key, secret):
    """Small stable settings/identity checkpoint; never returned to the browser."""
    base = "http://127.0.0.1:" + payload["compose"]["services"][key]["ports"][0]["published"]
    if key in {"tautulli", "kuma", "cleanuparr"}:
        from .companion_maintenance import checkpoint

        return await checkpoint(key, base, secret)
    headers = {"Accept": "application/json", "X-Plex-Token" if key == "plex" else "X-Api-Key": secret.get("api_key", "")}
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=5, headers=headers) as client:
        async def get(path):
            response, body = await bounded_response(client, "GET", base + path)
            response.raise_for_status()
            return json.loads(body)
        if key == "qbittorrent":
            response, _ = await bounded_response(client, "POST", base + "/api/v2/auth/login", data={"username": secret.get("username"), "password": secret.get("password")}, headers={"Referer": base})
            response.raise_for_status()
            preferences = await get("/api/v2/app/preferences")
            names = ("save_path", "temp_path", "temp_path_enabled", "max_connec", "web_ui_username", "web_ui_csrf_protection_enabled", "web_ui_host_header_validation_enabled")
            return {"preferences": {name: preferences.get(name) for name in names}, "categories": await get("/api/v2/torrents/categories")}
        if key == "plex":
            identity = (await get("/identity"))["MediaContainer"]["machineIdentifier"]
            sections = (await get("/library/sections"))["MediaContainer"].get("Directory", [])
            return {"identity": identity, "name": (await get("/"))["MediaContainer"].get("friendlyName"),
                    "libraries": sorted((row["key"], row["title"], row["type"]) for row in sections)}
        if key == "seerr":
            names = ("id", "name", "hostname", "port", "apiKey", "useSsl", "baseUrl", "activeProfileId", "activeProfileName",
                     "activeDirectory", "isDefault", "is4k", "tags", "syncEnabled", "preventSearch", "minimumAvailability",
                     "enableSeasonFolders", "seriesType", "animeSeriesType", "monitorNewItems", "overrideRule")
            result = {app: sorted([{name: row.get(name) for name in names} for row in await get("/api/v1/settings/" + app)], key=lambda row: row["id"]) for app in ("sonarr", "radarr")}
            result["plex"] = await get("/api/v1/settings/plex")
            main = await get("/api/v1/settings/main")
            result["authentication"] = {name: main.get(name) for name in
                ("mediaServerType", "mediaServerLogin", "newPlexLogin", "localLogin", "defaultPermissions")}
            async def records(path):
                rows = []
                for offset in range(0, 10000, 100):
                    page = (await get(path + ("&" if "?" in path else "?") + f"take=100&skip={offset}"))["results"]
                    if not isinstance(page, list):
                        raise DeploymentError("Seerr returned an invalid saved-record checkpoint.")
                    rows.extend(page)
                    if len(page) < 100:
                        return rows
                raise DeploymentError("Seerr's saved-record checkpoint is too large for this update preview. Keep the current version.")
            users = await records("/api/v1/user")
            result["users"] = sorted(({name: row.get(name) for name in ("id", "email", "username", "userType", "permissions", "plexId", "plexUsername")}
                                      for row in users), key=lambda row: row["id"])
            requests = await records("/api/v1/request?filter=all")
            result["requests"] = sorted(({**{name: row.get(name) for name in ("id", "status", "type", "is4k")},
                "requestedBy": (row.get("requestedBy") or {}).get("id"),
                "media": {name: (row.get("media") or {}).get(name) for name in ("id", "tmdbId", "tvdbId", "mediaType")}}
                for row in requests), key=lambda row: row["id"])
            return result
        api = "/api/v1" if key == "prowlarr" else "/api/v3"
        paths = ("applications",) if key == "prowlarr" else ("downloadclient", "rootfolder", "series" if key == "sonarr" else "movie")
        result = {"ui": await get(api + "/config/ui")}
        for path in paths:
            names = ("id", "path", "tvdbId", "tmdbId") if path in {"series", "movie"} else ("id", "path") if path == "rootfolder" else ("id", "name", "implementation", "fields")
            result[path] = sorted([{name: row.get(name) for name in names} for row in await get(api + "/" + path)], key=lambda row: row["id"])
            for row in result[path]:
                if "fields" in row:
                    row["fields"] = sorted([{name: field.get(name) for name in ("name", "value")} for field in row["fields"]], key=lambda field: field["name"])
        return result


class Updates:
    def __init__(self, deployments):
        self.deployments, self.store = deployments, deployments.store
        self.backups = AppBackups(deployments)
        initialize(self.store)

    def read(self, identity):
        if not re.fullmatch(r"[a-f0-9]{32}", identity):
            raise DeploymentError("Choose a saved update.")
        with self.store.db() as db:
            row = db.execute("SELECT state,phase,value FROM app_updates WHERE id=?", (identity,)).fetchone()
        if not row:
            raise DeploymentError("This update is unavailable.")
        return {"state": row[0], "phase": row[1], **json.loads(self.store.cipher.decrypt(row[2]))}

    def save(self, run, state, phase):
        run = {key: value for key, value in run.items() if key not in {"state", "phase"}}
        with self.store.db() as db:
            db.execute("INSERT INTO app_updates VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,phase=excluded.phase,updated=excluded.updated,value=excluded.value",
                       (run["id"], run["deployment"], run["app"], state, phase, run["created"], time.time(), self.store.cipher.encrypt(json.dumps(run).encode())))
            if state == "running":
                db.execute("UPDATE deployment_actions SET message=?,updated=? WHERE state='running'", (CATALOG[run["app"]]["name"] + ": " + PHASES.get(phase, "Working"), time.time()))

    def listing(self):
        record = catalog()
        rows = []
        with self.store.db() as db:
            installs = db.execute("SELECT id,payload FROM deployments WHERE state='needs-setup'").fetchall()
            history = db.execute("SELECT id,deployment,app,state,phase,updated FROM app_updates ORDER BY created DESC LIMIT 30").fetchall()
        for identity, raw in installs:
            payload = json.loads(raw)
            for key in payload["apps"]:
                if key not in record["apps"]:
                    continue
                target = record["apps"][key]
                rows.append({"deployment": identity, "app": key, "name": CATALOG[key]["name"],
                             "target_version": target["version"], "available": payload["compose"]["services"][key]["image"] != target["image"]})
        return {"reviewed_on": record["reviewed_on"], "apps": rows,
                "history": [{"id": row[0], "deployment": row[1], "app": row[2], "name": CATALOG[row[2]]["name"],
                             "state": row[3], "phase": PHASES.get(row[4], "Operation recorded"), "updated": row[5]} for row in history]}

    def image(self, payload, reference):
        info = json.loads(self.deployments._call(["--context", payload["context"]["name"], "image", "inspect", reference]))[0]
        if (info.get("Os") != "linux" or info.get("Architecture") != "amd64"
                or not re.fullmatch(r"sha256:[a-f0-9]{64}", info.get("Id", ""))):
            raise DeploymentError("This image does not match the supported Linux x64 runtime.")
        return info

    def owned(self, identity, payload, key, expected_id=None, allow_stopped=True):
        info = inspect_container(self.deployments, identity, payload, key)
        service = payload["compose"]["services"][key]
        state = info.get("State", {})
        if (differences(info, app_project(identity, payload), key, service)
                or (info.get("Config", {}).get("Labels") or {}).get(LABEL) != service.get("labels", {}).get(LABEL)
                or state.get("Paused") or state.get("Restarting") and not allow_stopped
                or not re.fullmatch(r"[a-f0-9]{64}", info.get("Id", ""))
                or expected_id and info["Id"] != expected_id
                or not allow_stopped and not state.get("Running")):
            raise DeploymentError("App identity or installation settings changed. No unverified container will be replaced.")
        environment = dict(item.split("=", 1) for item in info.get("Config", {}).get("Env", []) if "=" in item)
        if any(environment.get(k) != str(v) for k, v in service.get("environment", {}).items()):
            raise DeploymentError("App environment changed. Preserve and review those settings before updating.")
        volume = app_project(identity, payload) + "_" + key + "-config"
        context = payload["context"]["name"]
        details = json.loads(self.deployments._call(["--context", context, "volume", "inspect", volume]))[0]
        labels = details.get("Labels") or {}
        consumers = self.deployments._call(["--context", context, "ps", "-aq", "--no-trunc", "--filter", "volume=" + volume]).split()
        if (consumers != [info["Id"]] or labels.get("com.docker.compose.project") != app_project(identity, payload)
                or labels.get("com.docker.compose.volume") != key + "-config"):
            raise DeploymentError("The app configuration volume is shared or changed. Keep it unchanged until reviewed.")
        self.auxiliary(payload, key, info)
        return info

    def auxiliary(self, payload, key, info):
        from .app_maintenance import AppMaintenance

        expected = {mount["target"] for mount in payload["compose"]["services"][key]["volumes"]}
        result = {}
        for mount in info.get("Mounts", []):
            if mount["Destination"] in expected:
                continue
            image = self.image(payload, payload["compose"]["services"][key]["image"])
            if key != "plex" or mount["Destination"] != "/transcode" or "/transcode" not in image.get("Config", {}).get("Volumes", {}):
                raise DeploymentError("An unreviewed extra volume is mounted. Keep the current app and review its storage.")
            result["/transcode"] = AppMaintenance(self.deployments).auxiliary(payload, mount.get("Name", ""), info["Id"])
        return result

    def review(self, identity, key, action="update", update=None):
        if action == "update":
            payload = load_receipt(self.deployments, identity)
            target = catalog()["apps"].get(key)
            if key not in payload["apps"] or not target:
                raise DeploymentError("Choose a supported app owned by this installation.")
            current = payload["compose"]["services"][key]["image"]
            if current == target["image"]:
                raise Conflict("This app already uses the packaged update candidate.")
            info = self.owned(identity, payload, key, allow_stopped=False)
            old_image = self.image(payload, current)
            old_version = (old_image.get("Config", {}).get("Labels") or {}).get("org.opencontainers.image.version", "")
            if key in {"tautulli", "kuma"}:
                # These official images use a branch label or omit the version.
                # Bind the authenticated running version to the inspected image.
                old_version = asyncio.run(response_version(key, "http://127.0.0.1:" + payload["compose"]["services"][key]["ports"][0]["published"], self.credentials(identity, payload, key)))
            if not old_version or app_version(old_version).split(".")[0] != app_version(target["version"]).split(".")[0] or version_order(target["version"]) <= version_order(old_version):
                raise DeploymentError("A compatible same-major update could not be verified. Keep the current version.")
            return {"deployment": identity, "app": key, "name": CATALOG[key]["name"], "action": action,
                    "container": info["Id"], "receipt": self.deployments.actions.fingerprint(payload),
                    "target": target, "current_version": old_version, "old_image_id": old_image["Id"],
                    "auxiliary": self.auxiliary(payload, key, info)}
        if action not in {"rollback", "update-recover"} or not update:
            raise DeploymentError("Choose a saved update to roll back or recover.")
        run = self.read(update)
        if run["deployment"] != identity or run["app"] != key:
            raise DeploymentError("This update belongs to a different app.")
        if action == "rollback" and run["state"] != "succeeded" or action == "update-recover" and run["state"] != "needs-recovery":
            raise Conflict("Check the current update state and review again.")
        if action == "rollback":
            expected = load_receipt(self.deployments, identity)
            if compatibility(expected) != compatibility(run["new"]):
                raise DeploymentError("A later update changed this installation. Roll back its latest compatible update first.")
        else:
            self.validate_files(run)
            expected = self.current_payload(run)
        info = None if action == "update-recover" and self.missing(run) else self.owned(identity, expected, key)
        if info and self.auxiliary(expected, key, info) != run.get("auxiliary", {}):
            raise DeploymentError("The app's retained scratch storage changed. Keep it unchanged and inspect recovery.")
        return {"deployment": identity, "app": key, "name": CATALOG[key]["name"], "action": action,
                "update": update, "container": info["Id"] if info else None, "run_state": run["state"], "run_phase": run["phase"],
                "receipt": self.deployments.actions.fingerprint(expected),
                "current_version": run["target"]["version"], "target": {"version": run["old_version"]}}

    @staticmethod
    def public(review):
        return {key: review[key] for key in ("deployment", "app", "name", "action", "current_version")} | {
            "target_version": review["target"]["version"],
            "notice": ("Download the pinned compatible image, stop only this app, save and verify an encrypted configuration snapshot, then recreate this app with its existing ports and storage. An authenticated health check must pass; failure restores the previous image and matching configuration. " if review["action"] == "update" else "Restore this app's previous image and its matching pre-update configuration. Settings added after the update will be replaced; a safety copy of the current configuration is kept first. " if review["action"] == "rollback" else "Recover the interrupted operation using its saved image/configuration pair. ")
            + "Playback or active work in this app is interrupted. Other apps are preserved. Stackarr never deletes or restores media/download files. Keep the controller data directory and encryption key."}

    def credentials(self, identity, payload, key):
        secret = self.store.secret(key)
        if key in {"plex", "seerr"}:
            from .finish_setup import read_candidate

            secret = read_candidate(self.deployments, identity, payload, key, self.store.config()[1].integrations[key])
        if not secret:
            raise DeploymentError("Finish the app's account/connection setup before updating.")
        if key in {"tautulli", "kuma", "cleanuparr"}:
            from .companions import Companions

            record = Companions(self.deployments).state(identity)["apps"].get(key, {})
            if not record.get("complete") or record.get("api_key") != secret.get("api_key"):
                raise DeploymentError("Finish companion setup and verify its saved login before updating.")
            secret = {**secret, **{name: record[name] for name in ("username", "password")}}
        return {**secret, "_deployment": identity, **({"_protected_version": 3} if key == "seerr" else {})}

    def protected(self, payload, key, secret):
        value = asyncio.run(protected_state(payload, key, secret))
        if key == "seerr" and secret.get("_protected_version", 1) == 1:
            # Older encrypted runs predate the Plex sign-in checkpoint. Keep
            # their exact recorded shape usable for recovery; new runs protect
            # the additional Plex sign-in fields.
            value.pop("authentication", None)
            for user in value["users"]:
                user.pop("plexId", None)
                user.pop("plexUsername", None)
        if key == "seerr" and secret.get("_protected_version", 1) >= 3:
            # A background Plex scan advances this cursor without changing
            # library selection or authentication. Keep all other fields.
            for library in value["plex"].get("libraries", []):
                library.pop("lastScan", None)
        if key in {"tautulli", "cleanuparr"}:
            from .companions import Companions

            identity = payload.get("identity") or secret.get("_deployment") or next(row["id"] for row in self.deployments.rows()
                if row["state"] == "needs-setup" and load_receipt(self.deployments, row["id"])["config"] == payload["config"])
            Companions(self.deployments).login(identity, key, payload)
            if key == "tautulli":
                config = Companions(self.deployments).tautulli_config(identity, payload)
                value["settings"] = {section: {name: config.get(section, name, fallback="") for name in names}
                    for section, names in {"General": ("http_username", "http_password", "http_hashed_password", "api_key", "first_run_complete"),
                                           "PMS": ("pms_identifier", "pms_ip", "pms_port", "pms_url", "pms_token")}.items()}
        return json.loads(json.dumps(value))

    def health(self, payload, key, secret, version, seconds=180):
        app = self.store.config()[1].integrations[key].model_copy(deep=True)
        app.url = "http://127.0.0.1:" + payload["compose"]["services"][key]["ports"][0]["published"]
        deadline, consecutive = time.monotonic() + seconds, 0
        while time.monotonic() < deadline:
            try:
                info = self.owned(payload["identity"], payload, key)
                if not info["State"].get("Running") or info["State"].get("Health", {}).get("Status") == "unhealthy":
                    consecutive = 0
                else:
                    asyncio.run(collect(key, app, secret))
                    actual_version = asyncio.run(response_version(key, app.url, secret))
                    if app_version(str(actual_version)) != app_version(version):
                        return False
                    consecutive += 1
                    if consecutive == 3:
                        return True
            except Exception:
                consecutive = 0
            time.sleep(2)
        return False

    def missing(self, run):
        context = run["old"]["context"]["name"]
        name = app_project(run["deployment"], run["old"]) + "-" + run["app"] + "-1"
        if self.deployments._call(["--context", context, "ps", "-aq", "--filter", "name=^/" + name + "$"]).strip():
            return False
        volume = app_project(run["deployment"], run["old"]) + "_" + run["app"] + "-config"
        labels = json.loads(self.deployments._call(["--context", context, "volume", "inspect", volume]))[0].get("Labels") or {}
        if (labels.get("com.docker.compose.project") != app_project(run["deployment"], run["old"])
                or labels.get("com.docker.compose.volume") != run["app"] + "-config"
                or self.deployments._call(["--context", context, "ps", "-aq", "--filter", "volume=" + volume]).strip()):
            raise DeploymentError("The missing app's configuration volume is shared or changed.")
        return True

    def stop(self, run, payload, require_clean=True):
        if not require_clean and self.missing(run):
            return
        info = self.owned(run["deployment"], payload, run["app"])
        if info["State"].get("Running"):
            self.deployments._call(["--context", payload["context"]["name"], "stop", "--timeout", "60", info["Id"]], timeout=90)
        info = self.owned(run["deployment"], payload, run["app"], info["Id"])
        if info["State"].get("Running") or require_clean and info["State"].get("ExitCode") == 137:
            raise DeploymentError("The app did not stop cleanly. Check its state before continuing.")

    def files(self, run):
        root = self.store.root / "deployments" / run["deployment"]
        paths = [root.parent, root, root / "compose.json"]
        for path in paths:
            if path.is_symlink() or path.is_junction():
                raise DeploymentError("Installation files must not be filesystem links.")
        return root / "compose.json"

    def validate_files(self, run):
        if self.deployments.context() != run["old"]["context"]:
            raise DeploymentError("Select the original local Docker context before recovery.")
        path = self.files(run)
        allowed = [run["old"], run["new"], run["previous"]]
        if path.read_text(encoding="utf-8") not in {json.dumps(p["compose"], sort_keys=True) for p in allowed}:
            raise DeploymentError("Installation files changed outside this update. Preserve those changes and review them first.")
        with self.store.db() as db:
            row = db.execute("SELECT payload FROM deployments WHERE id=?", (run["deployment"],)).fetchone()
        if not row or json.loads(row[0]) not in allowed:
            raise DeploymentError("The installation receipt changed outside this update.")

    def current_payload(self, run):
        if self.missing(run):
            return run["previous"]
        info = inspect_container(self.deployments, run["deployment"], run["old"], run["app"])
        for payload in (run["new"], run["previous"], run["old"]):
            try:
                self.owned(run["deployment"], payload, run["app"], info["Id"])
                if payload == run["old"] and info["Id"] != run["original_id"]:
                    continue
                return payload
            except DeploymentError:
                pass
        raise DeploymentError("No unchanged container matches this interrupted update. No unverified app will be adopted.")

    def commit(self, run, payload):
        self.validate_files(run)
        self.save(run, "running", "committing-receipt")
        path = self.files(run)
        temporary = path.with_name("compose-" + uuid.uuid4().hex + ".tmp")
        with temporary.open("x", encoding="utf-8") as out:
            out.write(json.dumps(payload["compose"], sort_keys=True))
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
        with self.store.db() as db:
            db.execute("UPDATE deployments SET payload=?,updated=? WHERE id=?", (json.dumps(payload), time.time(), run["deployment"]))

    def switch(self, run, payload, phase):
        self.validate_files(run)
        self.save(run, "running", phase)
        directory = self.files(run).parent
        path = directory / ("update-" + run["id"] + "-" + phase + ".json")
        plan = copy.deepcopy(payload["compose"])
        if run.get("auxiliary"):
            from .app_maintenance import AppMaintenance

            current = None if self.missing(run) else inspect_container(self.deployments, run["deployment"], payload, run["app"])
            for index, (destination, reference) in enumerate(run["auxiliary"].items()):
                if AppMaintenance(self.deployments).auxiliary(payload, reference["name"], current["Id"] if current else None) != reference:
                    raise DeploymentError("The saved Plex scratch volume changed. Recovery requires inspection.")
                alias = "retained-update-cache-" + str(index)
                plan["volumes"][alias] = {"external": True, "name": reference["name"]}
                plan["services"][run["app"]]["volumes"].append({"type": "volume", "source": alias, "target": destination})
        content = json.dumps(plan, sort_keys=True)
        if path.exists():
            if path.is_symlink() or path.is_junction() or path.read_text() != content:
                raise DeploymentError("Saved update plan changed. Keep the app stopped and review recovery.")
        else:
            with path.open("x", encoding="utf-8") as out:
                out.write(content)
        self.deployments._call(["--context", payload["context"]["name"], "compose", "--project-name", app_project(run["deployment"], run["old"]),
                                "-f", str(path), "up", "-d", "--no-deps", "--force-recreate", "--no-build", "--pull", "never", run["app"]], timeout=180)
        run["current_id"] = self.owned(run["deployment"], payload, run["app"])["Id"]
        if self.auxiliary(payload, run["app"], inspect_container(self.deployments, run["deployment"], payload, run["app"])) != run.get("auxiliary", {}):
            raise DeploymentError("The recreated app did not retain its reviewed scratch storage.")
        self.save(run, "running", phase + "-health")

    def snapshot(self, run, payload, stage, kind):
        review = {"deployment": run["deployment"], "receipt": compatibility(payload), "apps": [run["app"]]}
        return self.backups.snapshot(review, payload | {"identity": run["deployment"]}, stage, kind)

    def restore(self, run, payload, snapshot, stage):
        directory = stage / ("restore-" + uuid.uuid4().hex)
        directory.mkdir()
        self.backups.materialize(snapshot, directory)
        self.stop(run, self.current_payload(run), require_clean=False)
        self.backups.helper(payload | {"identity": run["deployment"]}, run["app"], directory / run["app"], restore=True)

    def recover_previous(self, run, stage):
        self.image(run["old"], run["old_image_id"])
        self.restore(run, run["previous"], run["backup"], stage)
        self.switch(run, run["previous"], "restoring-previous")
        if not self.health(run["previous"] | {"identity": run["deployment"]}, run["app"], run["secret"], run["old_version"]):
            raise DeploymentError("The previous app did not pass its recovery health check.")
        if run.get("protected") is not None and self.protected(run["previous"], run["app"], run["secret"]) != run["protected"]:
            raise DeploymentError("The recovered app settings did not match the saved checkpoint.")
        self.commit(run, run["previous"])
        self.save(run, "rolled-back", "previous-image-and-data-restored")

    def execute(self, review):
        if self.review(review["deployment"], review["app"], review["action"], review.get("update")) != review:
            raise Conflict("The reviewed app or update changed. Review again.")
        if review["action"] == "update":
            old = load_receipt(self.deployments, review["deployment"])
            from .bundled_images import verify

            if not verify(lambda args: self.deployments._call(["--context", old["context"]["name"], *args]), review["target"]["image"]):
                self.deployments._call(["--context", old["context"]["name"], "pull", "--platform", "linux/amd64", review["target"]["image"]], timeout=600)
            candidate = self.image(old, review["target"]["image"])
            version = (candidate.get("Config", {}).get("Labels") or {}).get("org.opencontainers.image.version", "")
            expected_label = review["target"].get("image_version", review["target"]["version"])
            revision = (candidate.get("Config", {}).get("Labels") or {}).get("org.opencontainers.image.revision", "")
            if version != expected_label or review["target"].get("image_revision", revision) != revision:
                raise DeploymentError("Candidate version metadata differs from the reviewed catalog. Current app is preserved.")
            self.owned(review["deployment"], old, review["app"], review["container"])
            secret = self.credentials(review["deployment"], old, review["app"])
            if not self.health(old | {"identity": review["deployment"]}, review["app"], secret, review["current_version"], seconds=30):
                raise DeploymentError("The current app must pass authenticated health checks before updating.")
            checkpoint = self.protected(old, review["app"], secret)
            identity = uuid.uuid4().hex
            new, previous = copy.deepcopy(old), copy.deepcopy(old)
            for payload in (new, previous):
                payload["compose"]["services"][review["app"]].setdefault("labels", {})[LABEL] = identity
            new["compose"]["services"][review["app"]]["image"] = review["target"]["image"]
            run = {"id": identity, "created": time.time(), "deployment": review["deployment"], "app": review["app"],
                   "old": old, "new": new, "previous": previous, "original_id": review["container"],
                   "old_image_id": review["old_image_id"], "old_version": review["current_version"],
                   "target": review["target"], "backup": None, "secret": secret, "protected": checkpoint,
                   "auxiliary": review.get("auxiliary", {})}
        else:
            run = self.read(review["update"])
            if review["action"] == "rollback":
                current = load_receipt(self.deployments, run["deployment"])
                # Keep operational labels from later, already-reverted updates on other services.
                for payload in (run["old"], run["previous"]):
                    for key, service in current["compose"]["services"].items():
                        if key != run["app"]:
                            payload["compose"]["services"][key] = copy.deepcopy(service)
                run["new"] = current
        self.save(run, "running", "preparing" if review["action"] == "update" else run["phase"])
        with tempfile.TemporaryDirectory(prefix="update-", dir=self.backups.root) as directory:
            stage = Path(directory)
            try:
                if review["action"] == "update":
                    self.deployments._call(["--context", run["old"]["context"]["name"], "tag", run["old_image_id"], "stackarr-update-recovery-" + run["id"] + ":previous"])
                    self.stop(run, run["old"])
                    run["backup"] = self.snapshot(run, run["old"], stage, "before-update")
                    verify = stage / "verify"
                    verify.mkdir()
                    self.backups.materialize(run["backup"], verify)
                    self.save(run, "running", "backup-verified")
                    self.switch(run, run["new"], "applying-candidate")
                    if not self.health(run["new"] | {"identity": run["deployment"]}, run["app"], run["secret"], run["target"]["version"]):
                        raise DeploymentError("Candidate failed authenticated health checks.")
                    if self.protected(run["new"], run["app"], run["secret"]) != run["protected"]:
                        raise DeploymentError("Candidate changed protected app settings or library connections.")
                    self.commit(run, run["new"])
                    self.save(run, "succeeded", "updated-and-healthy")
                    return {"state": "succeeded", "message": review["name"] + " updated and authenticated health checks passed. Previous image/configuration are retained for rollback. Media and downloads were untouched by Stackarr."}
                if review["action"] == "rollback":
                    try:
                        run["forward_protected"] = self.protected(run["new"], run["app"], run["secret"])
                    except Exception:
                        run["forward_protected"] = None
                    self.stop(run, run["new"])
                    run["forward_backup"] = self.snapshot(run, run["new"], stage, "before-rollback")
                    self.save(run, "running", "rollback-safety-saved")
                if run["backup"]:
                    self.recover_previous(run, stage)
                else:
                    info = self.owned(run["deployment"], run["old"], run["app"], run["original_id"])
                    if not info["State"].get("Running"):
                        self.deployments._call(["--context", run["old"]["context"]["name"], "start", info["Id"]], timeout=60)
                    if not self.health(run["old"] | {"identity": run["deployment"]}, run["app"], run["secret"], run["old_version"]):
                        raise DeploymentError("The original app did not pass recovery health checks.")
                    self.save(run, "rolled-back", "original-app-preserved")
                return {"state": "succeeded", "message": review["name"] + " recovered with its previous image and matching settings. Media and downloads were untouched by Stackarr."}
            except Exception as exc:
                run["failure"] = str(exc) if isinstance(exc, (DeploymentError, Conflict)) else type(exc).__name__
                self.save(run, "running", run.get("phase", "recovery-review-required"))
                if review["action"] == "update":
                    try:
                        if run["backup"]:
                            self.recover_previous(run, stage)
                        else:
                            info = self.owned(run["deployment"], run["old"], run["app"], run["original_id"])
                            if not info["State"].get("Running"):
                                self.deployments._call(["--context", run["old"]["context"]["name"], "start", info["Id"]], timeout=60)
                            if not self.health(run["old"] | {"identity": run["deployment"]}, run["app"], run["secret"], run["old_version"]):
                                raise DeploymentError("The original app is not ready for recovery.")
                            self.save(run, "rolled-back", "original-app-preserved")
                        return {"state": "rolled-back", "message": review["name"] + " update failed. Previous image and settings recovered; media/download files were preserved. Check Health before retrying."}
                    except Exception:
                        pass
                elif run.get("forward_backup"):
                    try:
                        self.restore(run, run["new"], run["forward_backup"], stage)
                        self.switch(run, run["new"], "restoring-current")
                        if not self.health(run["new"] | {"identity": run["deployment"]}, run["app"], run["secret"], run["target"]["version"]):
                            raise DeploymentError("Current app failed recovery health checks.")
                        if run.get("forward_protected") is not None and self.protected(run["new"], run["app"], run["secret"]) != run["forward_protected"]:
                            raise DeploymentError("Current settings did not match the safety checkpoint.")
                        self.commit(run, run["new"])
                        self.save(run, "succeeded", "rollback-failed-current-restored")
                        return {"state": "rolled-back", "message": "Rollback failed; the current image and its newer settings were recovered from the safety snapshot. Check Health."}
                    except Exception:
                        pass
                self.save(run, "needs-recovery", "recovery-review-required")
                raise DeploymentError("Update recovery needs attention. Keep the saved snapshots; use Recover interrupted update in Apps. No media was deleted by Stackarr.") from None
