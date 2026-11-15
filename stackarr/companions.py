"""Reviewed first-run setup of owned companions; cleanup remains disabled."""

import configparser
import json
import re
import secrets
import time
import xml.etree.ElementTree as ET

import httpx

from .adapters import CLEANUP_FLAGS, require_write
from .config import CATALOG
from .deployment import DeploymentError
from .deployment_check import differences, inspect_container, load_receipt
from .docker_names import app_project
from .kuma import Kuma
from .lifecycle import Lifecycle
from .store import Conflict

APPS = {"tautulli", "kuma", "cleanuparr"}
CLEANUP_JOBS = ("queue_cleaner", "download_cleaner", "malware_blocker", "seeker", "blacklist_sync")


def reply(client, method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    response.raise_for_status()
    if len(response.content) > 2 * 1024 * 1024:
        raise DeploymentError("A companion returned too much configuration data.")
    return response.json() if response.content else {}


def cleanup_safe(client):
    general = reply(client, "GET", "/api/configuration/general")
    if general.get("dryRun") is not True or general.get("auth", {}).get("disableAuthForLocalAddresses"):
        raise DeploymentError("Cleanuparr's dry-run or authentication settings changed. Existing settings were preserved; review them in Cleanuparr.")
    for job in CLEANUP_JOBS:
        value = reply(client, "GET", "/api/configuration/" + job)
        if any(value.get(flag) is not False for flag in CLEANUP_FLAGS[job]):
            raise DeploymentError("A Cleanuparr job was enabled outside Stackarr. Existing settings were preserved; disable it before using the safe setup again.")
    return general


class Companions:
    def __init__(self, deployments):
        self.deployments, self.store = deployments, deployments.store

    def state(self, identity):
        return self.store.secret("companions:" + identity) or {"apps": {}}

    def save(self, identity, value):
        with self.store.db() as db:
            db.execute("INSERT OR REPLACE INTO secrets VALUES(?,?)", ("companions:" + identity,
                       self.store.cipher.encrypt(json.dumps(value).encode())))

    def owned(self, identity, key, payload=None):
        payload = payload or load_receipt(self.deployments, identity)
        info = inspect_container(self.deployments, identity, payload, key)
        if (self.deployments.context() != payload["context"]
                or differences(info, app_project(identity, payload), key, payload["compose"]["services"][key])
                or not info["State"].get("Running") or info["State"].get("Paused") or info["State"].get("Restarting")
                or not re.fullmatch(r"[a-f0-9]{64}", info.get("Id", ""))):
            raise DeploymentError("A companion or source app changed. Check its owned installation before setup.")
        if key in APPS and any(mount["Type"] != "volume" for mount in info["Mounts"]):
            raise DeploymentError("Companions must not have media, download or Docker socket mounts.")
        return info

    def sources(self):
        config = self.store.config()[1]
        result = {}
        for row in self.deployments.rows():
            if row["state"] != "needs-setup":
                continue
            payload = load_receipt(self.deployments, row["id"])
            for key in payload["apps"]:
                port = int(payload["compose"]["services"][key]["ports"][0]["published"])
                app = config.integrations[key]
                if not app.enabled or app.url != f"http://127.0.0.1:{port}":
                    continue
                info = self.owned(row["id"], key, payload)
                if key in result:
                    raise DeploymentError("Multiple owned apps match this source. Review their connections first.")
                result[key] = {"deployment": row["id"], "container": info["Id"], "port": port,
                               "receipt": Lifecycle.fingerprint(payload)}
        return result

    def review(self, identity):
        payload = load_receipt(self.deployments, identity)
        selected = [key for key in payload["apps"] if key in APPS]
        if not selected:
            raise DeploymentError("Choose an owned companion installation.")
        containers = {key: self.owned(identity, key, payload)["Id"] for key in selected}
        sources = self.sources()
        if "tautulli" in selected and "plex" not in sources:
            raise DeploymentError("Connect an owned Plex server before setting up Tautulli.")
        return {"action": "companions", "deployment": identity, "name": "Companion setup", "apps": selected,
                "containers": containers, "receipt": Lifecycle.fingerprint(payload),
                "revision": self.store.config()[0], "sources": sources}

    @staticmethod
    def public(review):
        return {"action": "companions", "deployment": review["deployment"], "name": review["name"],
                "apps": [CATALOG[key]["name"] for key in review["apps"]],
                "notice": "Create generated local logins only for newly owned companions. Link Tautulli to the owned Docker Plex server and add TCP availability monitors in Kuma for the installed apps. Connect Cleanuparr to owned Sonarr, Radarr and qBittorrent with dry-run enabled and every automatic job disabled. Existing accounts, monitors and connections are preserved. No media/download folders or Docker socket are mounted; no cleanup or media deletion is requested."}

    def credential(self, key, source):
        if key == "plex":
            from .finish_setup import read_candidate

            payload = load_receipt(self.deployments, source["deployment"])
            value = read_candidate(self.deployments, source["deployment"], payload, key,
                                   self.store.config()[1].integrations[key])
        else:
            value = self.store.secret(key)
        if not value:
            raise DeploymentError("Finish connecting the source app before companion setup.")
        return value

    @staticmethod
    def client(port):
        return httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=25, trust_env=False, follow_redirects=False)

    def tautulli_config(self, identity, payload):
        info = self.owned(identity, "tautulli", payload)
        raw = self.deployments._call(["--context", payload["context"]["name"], "exec", info["Id"], "cat", "/config/config.ini"])
        if len(raw) > 256000:
            raise DeploymentError("Unexpected Tautulli configuration size.")
        config = configparser.ConfigParser(interpolation=None, strict=False)
        config.read_string(raw)
        return config

    @staticmethod
    def tautulli_session(client, path):
        response = client.get(path)
        response.raise_for_status()
        token = re.search(r'<meta name="csrf-token" content="([A-Za-z0-9_-]{16,128})">', response.text)
        if not token:
            raise DeploymentError("Tautulli's protected setup page is unavailable.")
        client.headers["X-CSRF-Token"] = token[1]

    def tautulli(self, identity, payload, record, save, sources):
        source = sources["plex"]
        token = self.credential("plex", source)["api_key"]
        with self.client(source["port"]) as plex:
            response = plex.get("/identity", headers={"X-Plex-Token": token})
            response.raise_for_status()
            machine = ET.fromstring(response.content).attrib["machineIdentifier"]
        port = payload["compose"]["services"]["tautulli"]["ports"][0]["published"]
        with self.client(port) as client:
            config = self.tautulli_config(identity, payload)
            complete = config.get("General", "first_run_complete", fallback="0") == "1"
            if not complete:
                self.tautulli_session(client, "/welcome")
                reply(client, "POST", "/save_pms_token", data={"token": token})
                result = client.post("/configUpdate", data={"first_run": "1", "api_enabled": "1", "http_username": record["username"],
                    "http_password": record["password"], "http_plex_admin": "1", "pms_ip": "host.docker.internal", "pms_port": str(source["port"]),
                    "pms_identifier": machine, "pms_url_manual": "1", "pms_url": f"http://host.docker.internal:{source['port']}",
                    })
                result.raise_for_status()
                config = self.tautulli_config(identity, payload)
            self.tautulli_session(client, "/auth/login")
            login = reply(client, "POST", "/auth/signin", data={"username": record["username"], "password": record["password"], "admin_login": "1"})
            if login.get("status") != "success":
                raise DeploymentError("Tautulli has an existing or changed login. It was preserved.")
            key = config.get("General", "api_key", fallback="").strip('"')
            if (not re.fullmatch(r"[a-fA-F0-9]{32}", key) or config.get("PMS", "pms_identifier", fallback="").strip('"') != machine
                    or config.get("PMS", "pms_url", fallback="").strip('"').rstrip("/") != f"http://host.docker.internal:{source['port']}"
                    or record.get("api_key", key) != key):
                raise DeploymentError("Tautulli's Plex connection or API key changed. Existing settings were preserved.")
            current_token = config.get("PMS", "pms_token", fallback="").strip('"')
            if current_token and current_token != token:
                raise DeploymentError("Tautulli's Plex credential changed. It was preserved.")
            if not current_token:
                # Resume only after proving the generated login and unchanged owned target.
                self.tautulli_session(client, "/settings")
                reply(client, "POST", "/save_pms_token", data={"token": token})
            server = reply(client, "GET", "/api/v2", params={"apikey": key, "cmd": "get_server_info"})
            if server.get("response", {}).get("data", {}).get("pms_identifier") != machine:
                raise DeploymentError("Tautulli could not verify the owned Docker Plex server.")
            value = reply(client, "GET", "/api/v2", params={"apikey": key, "cmd": "get_activity"})
            if (value.get("response", {}).get("result") != "success"
                    or not isinstance(value.get("response", {}).get("data", {}).get("sessions"), list)):
                raise DeploymentError("Tautulli's authenticated monitoring check failed.")
            record.update(api_key=key, complete=True, plex_identifier=machine)
            save()

    def kuma(self, identity, payload, record, save, sources):
        port = payload["compose"]["services"]["kuma"]["ports"][0]["published"]
        with Kuma(f"http://127.0.0.1:{port}") as socket:
            if socket.call("needSetup"):
                socket.call("setup", record["username"], record["password"])
            socket.login(record)
            if not record.get("api_key"):
                socket.call("getAPIKeyList")
                keys = socket.events.get("apiKeyList", [[]])[0]
                if any(row.get("name") == "Stackarr monitoring" for row in keys):
                    raise DeploymentError("A Kuma key was created before setup was interrupted. Preserve it and finish metrics setup in Kuma.")
                value = socket.call("addAPIKey", {"name": "Stackarr monitoring", "active": True, "expires": None})
                record["api_key"] = value["key"]
                save()
            monitors = socket.monitors()
            for key, source in sources.items():
                name = "Stackarr · " + CATALOG[key]["name"]
                existing = next((row for row in monitors if row.get("name") == name), None)
                if existing:
                    if existing.get("type") != "port" or existing.get("hostname") != "host.docker.internal" or int(existing.get("port", 0)) != source["port"]:
                        raise DeploymentError("A Stackarr Kuma monitor changed. It was preserved.")
                    continue
                socket.call("add", {"name": name, "type": "port", "hostname": "host.docker.internal", "port": source["port"],
                    "interval": 20, "retryInterval": 20, "maxretries": 0, "resendInterval": 0,
                    "active": True, "notificationIDList": {}, "upsideDown": False,
                    "accepted_statuscodes": ["200-299"], "timeout": 10,
                    "conditions": [], "kafkaProducerBrokers": [], "kafkaProducerSaslOptions": {}, "rabbitmqNodes": []})
            record.update(complete=True, monitor_count=len(sources))
            save()

    def cleanup(self, identity, payload, record, save, sources):
        port = payload["compose"]["services"]["cleanuparr"]["ports"][0]["published"]
        with self.client(port) as client:
            status = reply(client, "GET", "/api/auth/status")
            if not status.get("setupCompleted"):
                if not record.get("account_created"):
                    reply(client, "POST", "/api/auth/setup/account", json={"username": record["username"], "password": record["password"]})
                    record["account_created"] = True
                    save()
                reply(client, "POST", "/api/auth/setup/complete")
            login = reply(client, "POST", "/api/auth/login", json={"username": record["username"], "password": record["password"]})
            if login.get("requiresTwoFactor") or not login.get("tokens", {}).get("accessToken"):
                raise DeploymentError("Cleanuparr's existing login needs owner attention. It was preserved.")
            client.headers["Authorization"] = "Bearer " + login["tokens"]["accessToken"]
            api_key = reply(client, "GET", "/api/account/api-key")["apiKey"]
            if record.get("api_key", api_key) != api_key:
                raise DeploymentError("Cleanuparr's API key changed. It was preserved.")
            record["api_key"] = api_key
            save()
            if not record.get("safe_configured"):
                general = reply(client, "GET", "/api/configuration/general")
                general.update(dryRun=True, statusCheckEnabled=False)
                general["auth"] = general.get("auth", {}) | {"disableAuthForLocalAddresses": False, "trustForwardedHeaders": False, "trustedNetworks": []}
                reply(client, "PUT", "/api/configuration/general", json=general)
                for job in CLEANUP_JOBS:
                    config = reply(client, "GET", "/api/configuration/" + job)
                    if any(config.get(flag) is not False for flag in CLEANUP_FLAGS[job]):
                        reply(client, "PUT", "/api/configuration/" + job, json=config | dict.fromkeys(CLEANUP_FLAGS[job], False))
                cleanup_safe(client)
                record["safe_configured"] = True
                save()
            cleanup_safe(client)  # Always before passing upstream credentials.
            for key in ("sonarr", "radarr"):
                if key not in sources:
                    continue
                source = sources[key]
                value = {"name": "Stackarr " + CATALOG[key]["name"], "url": f"http://host.docker.internal:{source['port']}",
                         "apiKey": self.credential(key, source)["api_key"], "version": 4 if key == "sonarr" else 6, "enabled": True}
                current = reply(client, "GET", "/api/configuration/" + key)
                existing = next((row for row in current.get("instances", []) if row.get("name") == value["name"]), None)
                if existing and existing.get("url", "").rstrip("/") != value["url"]:
                    raise DeploymentError("An existing Cleanuparr Arr connection changed. It was preserved.")
                reply(client, "POST", "/api/configuration/" + key + "/instances/test", json=value)
                if not existing:
                    reply(client, "POST", "/api/configuration/" + key + "/instances", json=value)
            if "qbittorrent" in sources:
                source = sources["qbittorrent"]
                secret = self.credential("qbittorrent", source)
                value = {"name": "Stackarr qBittorrent", "typeName": "qBittorrent", "host": f"http://host.docker.internal:{source['port']}",
                         "enabled": True, "username": secret["username"], "password": secret["password"]}
                clients = reply(client, "GET", "/api/configuration/download_client")["clients"]
                existing = next((row for row in clients if row.get("name") == value["name"]), None)
                if existing and existing.get("host", "").rstrip("/") != value["host"]:
                    raise DeploymentError("An existing Cleanuparr download connection changed. It was preserved.")
                reply(client, "POST", "/api/configuration/download_client/test", json=value)
                if not existing:
                    reply(client, "POST", "/api/configuration/download_client", json=value)
            cleanup_safe(client)
            record["complete"] = True
            save()

    def execute(self, review):
        if self.review(review["deployment"]) != review:
            raise Conflict("The companion or source installation changed. Review setup again.")
        identity = review["deployment"]
        payload = load_receipt(self.deployments, identity)
        state = self.state(identity)
        for key in review["apps"]:
            require_write(key, "initial-login.create")
            if key not in state["apps"]:
                state["apps"][key] = {"username": "stackarr", "password": secrets.token_urlsafe(32)}
                self.save(identity, state)
            record = state["apps"][key]
            with self.store.db() as db:
                db.execute("UPDATE deployment_actions SET message=?,updated=? WHERE state='running'",
                           ("Preparing " + CATALOG[key]["name"] + " safely", time.time()))
            getattr(self, {"tautulli": "tautulli", "kuma": "kuma", "cleanuparr": "cleanup"}[key])(
                identity, payload, record, lambda: self.save(identity, state), review["sources"])
        config = self.store.config()[1]
        self.store.save(config, review["revision"], {key: {"api_key": state["apps"][key]["api_key"]} for key in review["apps"]})
        return "Companions prepared with generated logins. Tautulli and Kuma monitor the owned apps; Cleanuparr stays in dry-run with all cleanup jobs disabled. Choose Finish connecting to save monitoring privately."

    def connections(self, identity, payload=None):
        payload = payload or load_receipt(self.deployments, identity)
        state, result = self.state(identity), {}
        for key in payload["apps"]:
            if key not in APPS:
                continue
            self.owned(identity, key, payload)
            record = state["apps"].get(key, {})
            port = int(payload["compose"]["services"][key]["ports"][0]["published"])
            credential = {"api_key": record["api_key"]} if record.get("complete") else None
            if credential and self.store.secret(key) != credential:
                raise DeploymentError("The saved companion connection changed. It was preserved.")
            result[key] = {"port": port, "credential": credential}
        return {"id": identity, "apps": result}

    def login(self, identity, key, payload=None):
        if key not in APPS:
            raise DeploymentError("Choose an owned companion.")
        value = self.connections(identity, payload)["apps"].get(key)
        record = self.state(identity)["apps"].get(key, {})
        if not value or not value["credential"]:
            raise DeploymentError("Finish companion setup first.")
        port = value["port"]
        if key == "kuma":
            with Kuma(f"http://127.0.0.1:{port}") as client:
                client.login(record)
        else:
            with self.client(port) as client:
                if key == "tautulli":
                    self.tautulli_session(client, "/auth/login")
                response = reply(client, "POST", "/auth/signin" if key == "tautulli" else "/api/auth/login",
                    **({"data": {"username": record["username"], "password": record["password"], "admin_login": "1"}} if key == "tautulli" else {"json": {"username": record["username"], "password": record["password"]}}))
                if key == "tautulli" and response.get("status") != "success" or key == "cleanuparr" and not response.get("tokens", {}).get("accessToken"):
                    raise DeploymentError("The companion login changed. Use its existing login.")
        return {"id": identity, "app": key, "port": port, "api_key": value["credential"]["api_key"],
                "login": {field: record[field] for field in ("username", "password")}}
