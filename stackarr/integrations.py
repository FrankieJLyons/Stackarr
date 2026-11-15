"""Bounded read-only collectors. Never read local application databases or change downloads."""

import asyncio
import hashlib
import json
import time
from urllib.parse import urlsplit

import httpx

from .adapters import ADAPTERS
from .config import CATALOG, container_port
from .lan import browser_url
from .notifications import Notifications

RESPONSE_LIMIT = 4_000_000
RESPONSE_SECONDS = 12


class IntegrationError(Exception):
    def __init__(self, message, code="invalid-response"):
        super().__init__(message)
        self.code = code


async def bounded_response(client, method, url, **kwargs):
    """Bound bytes while reading, including endless or slowly trickling responses."""
    try:
        async with asyncio.timeout(RESPONSE_SECONDS):
            async with client.stream(method, url, **kwargs) as response:
                content = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    if len(content) + len(chunk) > RESPONSE_LIMIT:
                        raise IntegrationError("Response exceeds the collection limit.", "response-limit")
                    content.extend(chunk)
                return response, bytes(content)
    except TimeoutError:
        raise IntegrationError("Application response took too long. Check the app and try again.", "connection") from None


def records(value):
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise IntegrationError(
            "Unexpected API data shape; update the adapter or check the application version."
        )
    return value


def queue_state(row):
    state = row.get("trackedDownloadState", "")
    if state == "importing":
        return "importing"
    if state in ("importPending", "importBlocked", "importFailed"):
        return "awaiting import" if state == "importPending" else "blocked"
    if row.get("status") in ("failed", "warning"):
        return "blocked"
    if row.get("status") == "completed":
        return "awaiting import"
    return row.get("status", "unknown")


def torrent_state(value):
    if value in ("stalledDL", "metaDL"):
        return "stalled"
    if value in ("error", "missingFiles"):
        return "blocked"
    if value in ("uploading", "stalledUP", "forcedUP", "queuedUP"):
        return "seeding"
    if value in ("downloading", "forcedDL", "queuedDL", "allocating"):
        return "downloading"
    return value or "unknown"


async def collect(app, integration, secret, transport=None):
    base = integration.url or f"http://{app}:{container_port(app, integration)}"
    parsed = urlsplit(base)
    # Authenticated administrators may connect to LAN hosts; metadata endpoints are never integrations.
    if parsed.hostname in ("169.254.169.254", "metadata.google.internal"):
        raise IntegrationError("Cloud metadata endpoints are not valid integrations.")
    headers = {"Accept": "application/json"}
    if secret.get("api_key"):
        headers["X-Plex-Token" if app == "plex" else "X-Api-Key"] = secret["api_key"]
    if integration.request_host:
        headers["Host"] = integration.request_host
    async with httpx.AsyncClient(
        timeout=5, follow_redirects=False, trust_env=False, transport=transport, headers=headers
    ) as client:

        async def request(path, params=None):
            for attempt in range(2):
                try:
                    response, content = await bounded_response(client, "GET", base + path, params=params)
                    if response.status_code in (401, 403):
                        raise IntegrationError(
                            "Credentials rejected. Review the saved credentials in Settings → App connections.", "authentication"
                        )
                    if response.is_redirect:
                        raise IntegrationError(
                            "Address redirects. Enter the final application address in Settings → App connections.", "redirect"
                        )
                    response.raise_for_status()
                    return json.loads(content)
                except (httpx.TimeoutException, httpx.ConnectError):
                    if attempt:
                        raise IntegrationError(
                            "Connection failed. Check the address, network and certificate trust.", "connection"
                        ) from None
                    await asyncio.sleep(0.1)
                except (httpx.HTTPError, ValueError):
                    raise IntegrationError(
                        "API request failed or returned invalid JSON. Check the application and API version."
                    ) from None

        tables = {}
        if app in ("sonarr", "radarr", "prowlarr"):
            api = "/api/v1" if app == "prowlarr" else "/api/v3"
            system = await request(api + "/system/status")
            if not isinstance(system, dict) or "version" not in system:
                raise IntegrationError("Unexpected system status response.")
            tables["health"] = [
                {
                    "title": r.get("source", "Application"),
                    "state": r.get("type"),
                    "detail": r.get("message", ""),
                }
                for r in records(await request(api + "/health"))
            ]
            if app == "prowlarr":
                tables["sources"] = [
                    {
                        "title": r.get("name"),
                        "state": "enabled" if r.get("enable") else "disabled",
                        "detail": r.get("protocol", ""),
                    }
                    for r in records(await request(api + "/indexer"))
                ]
            else:
                for key, path in (("queue", "/queue"), ("blocklist", "/blocklist")):
                    data = await request(api + path, {"page": 1, "pageSize": 1000})
                    rows = records(data.get("records"))
                    tables[key] = [
                        {
                            "title": r.get("title") or r.get("sourceTitle", "Unknown"),
                            "state": queue_state(r) if key == "queue" else "blocked",
                            "detail": r.get("errorMessage") or r.get("message", ""),
                            "id": r.get("id"),
                            "download_id": r.get("downloadId", ""),
                        }
                        for r in rows
                    ]
                    if data.get("totalRecords", len(rows)) > len(rows):
                        tables.setdefault("health", []).append(
                            {
                                "title": key,
                                "state": "limited",
                                "detail": "Showing first 1000 records; open the app for all records.",
                            }
                        )
        elif app == "seerr":
            status = await request("/api/v1/status", {"checkUpdateAvailable": "false"})
            if not isinstance(status, dict) or not isinstance(status.get("version"), str):
                raise IntegrationError("Unexpected Seerr status. Check the address and API version.")
            if not secret.get("api_key"):
                raise IntegrationError("Finish Seerr setup, then open Apps to finish connecting.", "authentication")
            counts = await request("/api/v1/request/count")
            required = ("total", "pending", "approved", "declined", "processing", "available")
            if isinstance(counts, dict) and "completed" in counts:
                required += ("completed",)
            if not isinstance(counts, dict) or any(type(counts.get(key)) is not int or counts[key] < 0 for key in required):
                raise IntegrationError("Unexpected Seerr request counts. Check the supported API version.")
            tables["health"] = [{"title": "Seerr", "state": "connected", "detail": "Request permissions and approvals are managed in Seerr."}]
            tables["requests"] = [{"title": key.capitalize(), "state": str(counts[key]), "detail": "Reported request count; open Seerr to manage."} for key in required]
        elif app == "qbittorrent":
            login, content = await bounded_response(
                client, "POST", base + "/api/v2/auth/login",
                data={"username": secret.get("username", ""), "password": secret.get("password", "")},
                headers={"Referer": base},
            )
            accepted = login.status_code == 204 or (login.status_code == 200 and content.strip() == b"Ok.")
            if not accepted:
                raise IntegrationError("qBittorrent login failed. Check credentials and allowed hosts.", "authentication")
            tables["downloads"] = [
                {
                    "title": r.get("name"),
                    "state": torrent_state(r.get("state")),
                    "detail": f"{round(float(r.get('progress', 0)) * 100, 1)}%",
                    "id": r.get("hash"),
                    "raw_state": r.get("state"),
                }
                for r in records(await request("/api/v2/torrents/info"))
            ]
        elif app == "plex":
            data = await request("/status/sessions")
            container = data.get("MediaContainer")
            if not isinstance(container, dict) or "size" not in container:
                raise IntegrationError("Unexpected Plex sessions response.")
            tables["streams"] = [
                {
                    "title": r.get("title", "Stream"),
                    "state": r.get("Player", {}).get("state", "playing"),
                    "detail": "transcoding" if r.get("TranscodeSession") else "direct play",
                }
                for r in records(container.get("Metadata", []))
            ]
        elif app == "tautulli":
            data = await request("/api/v2", {"apikey": secret.get("api_key", ""), "cmd": "get_activity"})
            response = data.get("response", {})
            if response.get("result") != "success":
                raise IntegrationError("Tautulli rejected the API request. Check the API key.", "authentication")
            activity = response.get("data")
            if not isinstance(activity, dict) or not isinstance(activity.get("sessions"), list):
                raise IntegrationError("Tautulli cannot read Plex activity yet. Check its Plex server connection.", "connection")
            tables["streams"] = [
                {
                    "title": r.get("full_title"),
                    "state": r.get("state", "playing"),
                    "detail": r.get("video_decision", ""),
                }
                for r in records(activity["sessions"])
            ]
        elif app == "kuma":
            # Public Prometheus endpoint is a supported interface, unlike direct database access.
            response, content = await bounded_response(client, "GET", base + "/metrics", auth=("", secret.get("api_key", "")))
            if response.status_code in (401, 403):
                raise IntegrationError("Metrics credentials rejected. Create a Kuma API key.", "authentication")
            response.raise_for_status()
            metrics = content.decode("utf-8")
            if "monitor_status" not in metrics:
                raise IntegrationError(
                    "No monitor metrics found. Configure a monitor and metrics access in Kuma."
                )
            import re

            tables["monitoring"] = []
            for line in metrics.splitlines():
                match = re.match(
                    r'monitor_status\{.*?monitor_name="((?:\\.|[^"\\])*)".*?\}\s+([0-9.]+)', line
                )
                if match:
                    tables["monitoring"].append(
                        {"title": match[1], "state": "up" if float(match[2]) == 1 else "down", "detail": ""}
                    )
        elif app == "cleanuparr":
            from .adapters import CLEANUP_FLAGS

            general = await request("/api/configuration/general")
            jobs = [await request("/api/configuration/" + job)
                    for job in ("queue_cleaner", "download_cleaner", "malware_blocker", "seeker", "blacklist_sync")]
            safe = general.get("dryRun") is True and all(row.get(flag) is False
                for job, row in zip(CLEANUP_FLAGS, jobs, strict=True) for flag in CLEANUP_FLAGS[job])
            observing = general.get('dryRun') is True
            tables["health"] = [{"title": "Cleanuparr safety mode", "state": "ok" if observing else "warning",
                "detail": "Dry-run on; automatic cleanup disabled." if safe else
                    "Dry-run on; scheduled checks simulate cleanup. Review results in Cleanuparr." if observing else
                    "Live cleanup may remove downloads or files. Review Cleanuparr in Settings → Recommended settings."}]
        return tables


class Collector:
    def __init__(self, store, transport=None):
        self.store = store
        self.transport = transport
        self.snapshots = {}
        self.lock = asyncio.Lock()
        self.notifications = Notifications(store, transport)

    def connection_key(self, key, integration):
        data = {"url": integration.url, "mode": integration.mode, "port": integration.port,
                "credentials": self.store.secret(key)}
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    async def refresh(self, maintenance=True):
        async with self.lock:
            revision, config = self.store.config()
            active = {k: v for k, v in config.integrations.items() if v.enabled}
            identities = {k: self.connection_key(k, v) for k, v in active.items()}
            self.snapshots = {
                k: v for k, v in self.snapshots.items() if k in active and v.get("connection") == identities[k]
            }

            async def one(key, integration):
                if ADAPTERS[key].status == "link-only":
                    return
                previous = self.snapshots.get(key, {})
                result = {
                    "revision": revision,
                    "connection": identities[key],
                    "attempted_at": time.time(),
                    "collected_at": previous.get("collected_at"),
                    "tables": previous.get("tables"),
                    "state": "unavailable",
                    "error": None,
                    "error_code": None,
                }
                try:
                    async with asyncio.timeout(45):
                        result["tables"] = await collect(
                            key, integration, self.store.secret(key), self.transport
                        )
                    result.update(state="ready", collected_at=time.time())
                except IntegrationError as exc:
                    result["error"] = str(exc)
                    result["error_code"] = exc.code
                except Exception:
                    result["error_code"] = "collection"
                    result["error"] = (
                        "Collection failed. Check application availability and supported API version."
                    )
                current = self.store.config()[1].integrations[key]
                if not current.enabled or self.connection_key(key, current) != identities[key]:
                    return
                self.snapshots[key] = result
                if previous.get("state") != result["state"]:
                    self.store.audit("integration." + result["state"], key)
                if maintenance and config.maintenance.notifications_enabled:
                    self.notifications.observe(key, result["state"])

            await asyncio.gather(*(one(k, v) for k, v in active.items()))
            if maintenance and config.maintenance.backups_enabled and self.store.claim_backup_schedule():
                try:
                    self.store.backup(config.maintenance.backup_retention)
                except (ValueError, OSError):
                    self.store.audit("backup.failed")
                    if config.maintenance.notifications_enabled:
                        self.notifications.observe("backup", "failed")
                else:
                    if config.maintenance.notifications_enabled:
                        self.notifications.observe("backup", "ready")
            if maintenance:
                await self.notifications.deliver()

    def view(self):
        revision, config = self.store.config()
        result = []
        for key in config.dashboard.order:
            integration = config.integrations[key]
            if not integration.enabled:
                continue
            snapshot = self.snapshots.get(key, {})
            if snapshot.get("connection") != self.connection_key(key, integration):
                snapshot = {}
            collected = snapshot.get("collected_at")
            result.append(
                {
                    "id": key,
                    "name": CATALOG[key]["name"],
                    "visible": integration.visible,
                    "url": browser_url(key, integration.browser_url
                    or integration.url
                    or f"http://localhost:{integration.port or CATALOG[key]['port']}"),
                    "state": "link-only" if ADAPTERS[key].status == "link-only" else snapshot.get("state", "pending"),
                    "capabilities": list(ADAPTERS[key].tables),
                    "tables": snapshot.get("tables"),
                    "collected_at": collected,
                    "attempted_at": snapshot.get("attempted_at"),
                    "stale": snapshot.get("state") != "ready" or collected is None or time.time() - collected > config.dashboard.stale_seconds,
                    "error": snapshot.get("error"),
                    "error_code": snapshot.get("error_code"),
                }
            )
        return {"generated_at": time.time(), "integrations": result, "collecting": self.lock.locked(),
                "summaries": {key: summarize(result, key) for key in ("downloads", "queue", "streams")}}


def summarize(integrations, table):
    relevant = [app for app in integrations if table in app["capabilities"]]
    # Tautulli usually observes the same Plex sessions: never add both totals.
    if table == "streams" and any(app["id"] == "plex" for app in relevant):
        relevant = [app for app in relevant if app["id"] == "plex"]
    fresh = [app for app in relevant if app["state"] == "ready" and not app["stale"]]
    state = "not-configured" if not relevant else "complete" if len(fresh) == len(relevant) else "partial" if fresh else "unavailable"
    return {"state": state,
            "count": sum(len((app["tables"] or {}).get(table, [])) for app in fresh) if fresh else None,
            "sources": [app["name"] for app in relevant],
            "missing": [app["name"] for app in relevant if app not in fresh]}
