"""Read native Arr configuration; import a connection, never move or rewrite an app.

Only fixed Windows application-data locations are inspected. Credentials stay on
the host until a short-lived review is redeemed over the private controller RPC.
No native database, service, download or configuration is written by this module.
"""

import asyncio
import hashlib
import json
import os
import re
import secrets
import time
import xml.etree.ElementTree as ET
from pathlib import Path, PureWindowsPath
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import Field

from .config import CATALOG, Model
from .integrations import IntegrationError, bounded_response
from .store import Conflict

NATIVE_APPS = ("sonarr", "radarr", "prowlarr", "plex")
NOTICE = ("Import the connection and a settings snapshot into Stackarr. The existing app keeps its "
          "folders, profiles, sources, downloads and startup. Stackarr will treat it as read-only; "
          "this does not move it into Docker or grant Stackarr control of its installation.")


class NativeIntent(Model):
    app: Literal["sonarr", "radarr", "prowlarr", "plex"]


class Snapshot(Model):
    app: Literal["sonarr", "radarr", "prowlarr", "plex"]
    version: str = Field(max_length=80)
    browser_address: str = Field(max_length=2048)
    root_folders: list[dict] = Field(default_factory=list, max_length=100)
    quality_profiles: list[dict] = Field(default_factory=list, max_length=100)
    download_clients: list[dict] = Field(default_factory=list, max_length=100)
    sources: list[dict] = Field(default_factory=list, max_length=100)
    linked_apps: list[dict] = Field(default_factory=list, max_length=100)


class NativeImportError(ValueError):
    pass


def require_writable(store, *apps):
    config = store.config()[1]
    if any(config.integrations[key].read_only for key in apps):
        raise ValueError("Imported native apps are read-only in Stackarr. Open the original app to change its settings.")


def _text(value, limit=1024):
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
        raise NativeImportError("Native app settings could not be safely read.")
    return value


def _rows(value):
    if not isinstance(value, list) or len(value) > 100 or any(not isinstance(r, dict) for r in value):
        raise NativeImportError("Native app settings exceed this import's supported limits.")
    return value


def _summary(row):
    return {"id": row["id"], "name": _text(row["name"], 256)} if type(row.get("id")) is int else _invalid()


def _invalid():
    raise NativeImportError("Native app settings have an unsupported format.")


def _qualities(items):
    result = []
    for item in _rows(items):
        if type(item.get("allowed")) is not bool:
            _invalid()
        if "quality" in item:
            quality = item["quality"]
            if not isinstance(quality, dict):
                _invalid()
            result.append({**_summary(quality), "allowed": item["allowed"]})
        else:
            # A profile's grouped qualities inherit the group's allowed flag.
            for quality in _qualities(item.get("items", [])):
                result.append({**quality, "allowed": item["allowed"] and quality["allowed"]})
    return result


def summarize(app, version, address, data):
    snapshot = Snapshot(app=app, version=_text(version, 80), browser_address=address)
    if app == "prowlarr":
        snapshot.sources = [{**_summary(r), "implementation": _text(r.get("implementation", ""), 128),
                             "enabled": r.get("enable") is True} for r in _rows(data["indexer"])]
        snapshot.linked_apps = [{**_summary(r), "implementation": _text(r.get("implementation", ""), 128),
                                "sync_level": _text(r.get("syncLevel", ""), 80)} for r in _rows(data["applications"])]
    else:
        if any(type(r.get("id")) is not int for r in _rows(data["rootfolder"])):
            _invalid()
        snapshot.root_folders = [{"id": r["id"], "path": _text(r["path"])} for r in _rows(data["rootfolder"])
                                ]
        snapshot.quality_profiles = [{**_summary(r), "upgrades": r.get("upgradeAllowed") is True,
                                      "qualities": _qualities(r.get("items", []))}
                                     for r in _rows(data["qualityprofile"])]
        snapshot.download_clients = [{**_summary(r), "implementation": _text(r.get("implementation", ""), 128),
                                       "enabled": r.get("enable") is True}
                                      for r in _rows(data["downloadclient"])]
    # Deliberately exclude provider fields: they contain passwords and API keys.
    if len(snapshot.model_dump_json().encode()) > 65536:
        raise NativeImportError("Native settings snapshot is too large to import.")
    return snapshot.model_dump()


class NativeImporter:
    def __init__(self, *, enabled=False, program_data=None, transport=None, clock=time.monotonic):
        self.root = Path(program_data or os.environ.get("ProgramData", "C:/ProgramData"))
        self.enabled = enabled and (os.name == "nt" or program_data is not None)
        self.transport, self.clock = transport, clock
        self.reviews = {}

    def configuration(self, app):
        NativeIntent(app=app)
        if not self.enabled:
            raise NativeImportError("Native import needs the updated Windows host controller.")
        path = self.root / CATALOG[app]["name"] / "config.xml"
        if any(p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction()) for p in (self.root, path.parent, path)):
            raise NativeImportError("Linked native configuration folders are not imported automatically.")
        try:
            with path.open("rb") as handle:
                raw = handle.read(65537)
            if len(raw) > 65536 or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
                _invalid()
            xml = ET.fromstring(raw)
            key = xml.findtext("ApiKey", "")
            port = int(xml.findtext("Port", "0"))
            base = xml.findtext("UrlBase", "") or ""
            if (not re.fullmatch(r"[a-fA-F0-9]{32}", key) or not 1 <= port <= 65535
                    or not re.fullmatch(r"(?:/[A-Za-z0-9_-]+)*/?", base)):
                _invalid()
        except (OSError, ValueError, ET.ParseError):
            raise NativeImportError("Native settings are missing, unreadable or unsupported. Keep the app running and check its Windows data folder.") from None
        return {"address": f"http://127.0.0.1:{port}" + base.rstrip("/"), "key": key,
                "hash": hashlib.sha256(raw).hexdigest(), "directory": path.parent}

    async def inspect(self, app):
        if app == 'plex':
            if not self.enabled:
                raise NativeImportError('Native Plex detection needs the updated Windows host controller.')
            from .native_plex import inspect

            try:
                return await inspect(self.transport)
            except (ValueError, OSError, httpx.HTTPError, IntegrationError, KeyError, TypeError):
                raise NativeImportError('Native Plex could not be verified. Open the native Plex server and finish its account setup first.') from None
        source = await asyncio.to_thread(self.configuration, app)
        prefix = "/api/v1/" if app == "prowlarr" else "/api/v3/"
        try:
            async with asyncio.timeout(12), httpx.AsyncClient(transport=self.transport, timeout=3,
                    follow_redirects=False, trust_env=False, headers={"X-Api-Key": source["key"]}) as client:
                async def get(tail):
                    response, content = await bounded_response(client, "GET", source["address"] + prefix + tail)
                    if response.status_code != 200:
                        raise NativeImportError("Native app did not accept its saved connection. Check that it is running.")
                    return json.loads(content)
                status = await get("system/status")
                # A Docker app with the same name is not the native instance.
                if (not isinstance(status, dict) or status.get("appName", "").lower() != app
                        or PureWindowsPath(status.get("appData", "")) != PureWindowsPath(source["directory"])):
                    raise NativeImportError("The responding app does not match this native configuration folder.")
                routes = ("indexer", "applications") if app == "prowlarr" else ("rootfolder", "qualityprofile", "downloadclient")
                data = {route: await get(route) for route in routes}
                snapshot = summarize(app, status["version"], source["address"], data)
                if source["key"] in json.dumps(snapshot):
                    raise NativeImportError("Native settings contain a credential in a display field; review them in the original app.")
                # Exclude changing free-space readings from the review fingerprint.
                if "rootfolder" in data:
                    data["rootfolder"] = snapshot["root_folders"]
                fingerprint = hashlib.sha256((source["hash"] + json.dumps(data, sort_keys=True)).encode()).hexdigest()
                if (await asyncio.to_thread(self.configuration, app))["hash"] != source["hash"]:
                    raise Conflict("Native configuration changed during inspection. Review again.")
                return {"snapshot": snapshot, "credential": {"api_key": source["key"]}, "fingerprint": fingerprint,
                        "source_directory": str(source["directory"])}
        except (httpx.HTTPError, IntegrationError, TimeoutError, KeyError, TypeError, AttributeError, ValueError) as exc:
            if isinstance(exc, NativeImportError):
                raise
            raise NativeImportError("Native app could not be verified. Check that it is running and reachable locally.") from None

    async def scan(self):
        async def check(app):
            try:
                result = await self.inspect(app)
                return {"app": app, "state": "verified", "snapshot": result["snapshot"]}
            except (NativeImportError, Conflict) as exc:
                return {"app": app, "state": "unavailable", "detail": str(exc)}
        return {"available": self.enabled, "apps": await asyncio.gather(*(check(app) for app in NATIVE_APPS)), "notice": NOTICE}

    async def review(self, app):
        self.reviews = {key: row for key, row in self.reviews.items() if row[0] > self.clock()}
        if len(self.reviews) >= 32:
            raise Conflict("Too many pending native imports. Wait a few minutes and review again.")
        result = await self.inspect(app)
        reference = secrets.token_urlsafe(32)
        self.reviews[reference] = (self.clock() + 300, app, result["fingerprint"])
        return {"review_reference": reference, "snapshot": result["snapshot"], "notice": NOTICE}

    async def redeem(self, reference):
        row = self.reviews.pop(reference, None)
        if not row or row[0] <= self.clock():
            raise Conflict("Native import review expired or was used. Review again.")
        result = await self.inspect(row[1])
        if result["fingerprint"] != row[2]:
            raise Conflict("Native settings changed since the preview. Review again.")
        return result  # Private transport only; never return this to a browser.


def target(store, app, address):
    revision, config = store.config()
    current = config.integrations[app]
    saved = store.secret("native-import:" + app)
    if current.enabled or current.url or store.secret(app):
        if not (current.read_only and saved and current.url == address and saved.get("address") == address
                and saved.get("credential_hash") == hashlib.sha256(json.dumps(store.secret(app), sort_keys=True).encode()).hexdigest()):
            raise Conflict("Stackarr already has a different connection for this app. Your saved connection is preserved.")
    return revision, config


def dashboard_address(snapshot, remote):
    address = snapshot["browser_address"]
    parsed = urlsplit(address)
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or not re.fullmatch(r"(?:/[A-Za-z0-9_-]+)*", parsed.path)):
        raise NativeImportError("Native connection address is invalid.")
    return address.replace("http://127.0.0.1:", "http://host.docker.internal:", 1) if remote else address


async def connect(store, bundle, expected, snapshot, *, remote=False, transport=None):
    validated = Snapshot.model_validate(bundle["snapshot"]).model_dump()
    if validated != snapshot:
        raise Conflict("The native settings preview changed. Review again.")
    app = validated["app"]
    credential = bundle["credential"]
    if (set(credential) != {"api_key"} or not isinstance(credential["api_key"], str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{8,512}" if app == 'plex' else r"[a-fA-F0-9]{32}", credential["api_key"])):
        raise NativeImportError("Native connection credentials are invalid.")
    address = dashboard_address(validated, remote)
    revision, config = target(store, app, address)
    if revision != expected:
        raise Conflict("Stackarr settings changed since the preview. Review again.")
    # Verify the dashboard route too: localhost on the host is not localhost in Docker.
    prefix = "/api/v1/" if app == "prowlarr" else "/api/v3/"
    headers = {"Accept": "application/json", "X-Plex-Token" if app == 'plex' else "X-Api-Key": credential["api_key"]}
    if remote and app != 'plex':
        # Windows Arr HTTP listeners can require their original loopback Host.
        # Keep that authority while Docker reaches Windows through its host route.
        headers["Host"] = urlsplit(validated["browser_address"]).netloc
    async with httpx.AsyncClient(transport=transport, timeout=3, trust_env=False, follow_redirects=False) as client:
        response, content = await bounded_response(client, "GET", address + ('/identity' if app == 'plex' else prefix + "system/status"), headers=headers)
        status = json.loads(content) if response.status_code == 200 else {}
        matches = (status.get('MediaContainer', {}).get('machineIdentifier') == bundle['source_directory']
                   and status.get('MediaContainer', {}).get('claimed') in (True, 1)) if app == 'plex' else (
                       status.get("appName", "").lower() == app and
                       PureWindowsPath(status.get("appData", "")) == PureWindowsPath(bundle["source_directory"]))
        if not matches:
            raise NativeImportError("Stackarr cannot reach this native app from its dashboard. Check its listening address and firewall; nothing was imported.")
    current = config.integrations[app]
    current.enabled, current.mode, current.read_only = True, "connect", True
    current.url, current.browser_url, current.peer_url = address, validated["browser_address"], ""
    current.request_host = headers.get("Host", "")
    current.port, current.quality_profile = 0, ""
    saved = {"snapshot": validated, "address": address, "imported_at": time.time(),
             "credential_hash": hashlib.sha256(json.dumps(credential, sort_keys=True).encode()).hexdigest()}
    # Credentials and sanitized settings are committed together under one revision check.
    revision = store.save(config, expected, {app: credential, "native-import:" + app: saved}, native_app=app)
    store.audit("native-import.connected", app)
    return {"app": app, "state": "connected", "read_only": True, "revision": revision, "snapshot": validated}


def imported(store):
    config = store.config()[1]
    return [saved["snapshot"] for app in NATIVE_APPS
            if (saved := store.secret("native-import:" + app)) and config.integrations[app].read_only
            and config.integrations[app].url == saved["address"]]
