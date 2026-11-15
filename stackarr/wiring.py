"""Explicit, previewed application connections. Never invoked by status collection."""
from urllib.parse import urlsplit

import httpx

from .adapters import require_write
from .config import CATALOG, container_port
from .integrations import IntegrationError
from .native_import import require_writable
from .store import Conflict


class WiringError(Exception):
    pass


def public_plan(plan):
    """Return a reviewable summary without credentials or API payloads.

    The internal plan is short-lived and bound to the reviewing session.
    It contains API keys and connection passwords, so it must never cross the
    browser/API boundary or appear in an audit record.
    """
    return {
        "revision": plan["revision"],
        "changes": [
            {
                "target": change["target"],
                "kind": change["kind"],
                "connection": change["name"],
                "implementation": change["implementation"],
                "action": change.get("action", "create after an API compatibility test"),
                **({"detail": change["detail"]} if change.get("detail") else {}),
            }
            for change in plan["changes"]
        ],
        "notices": plan["notices"],
        "checks": plan.get("checks", []),
    }


def address(key, integration):
    return integration.url or f"http://{key}:{container_port(key, integration)}"


def peer_address(key, integration):
    return integration.peer_url or address(key, integration)


async def build_plan(store, transport=None):
    revision, config = store.config()
    changes, notices, checks = [], [], []
    qbit = config.integrations["qbittorrent"]
    for target in ("sonarr", "radarr"):
        integration = config.integrations[target]
        if not integration.enabled:
            continue
        if integration.read_only:
            notices.append(f"{CATALOG[target]['name']}: imported native app is read-only; existing connections are preserved.")
            continue
        check = {"source": "qbittorrent", "target": target, "state": "unavailable"}
        if qbit.enabled:
            checks.append(check)
        key = store.secret(target).get("api_key")
        if not key:
            notices.append(f"{CATALOG[target]['name']}: save an API key first.")
            continue
        if qbit.enabled:
            credentials = store.secret("qbittorrent")
            if not credentials.get("username") or not credentials.get("password"):
                notices.append("Save qBittorrent username and password before creating download client connections.")
                continue
            parsed = urlsplit(peer_address("qbittorrent", qbit))
            fields = {"host": parsed.hostname, "port": parsed.port or (443 if parsed.scheme == "https" else 80),
                      "useSsl": parsed.scheme == "https", "urlBase": parsed.path,
                      "username": credentials["username"], "password": credentials["password"],
                      "category": target}
            changes.append({"source": "qbittorrent", "target": target, "check": check,
                            "base": address(target, integration), "key": key,
                            "path": "/api/v3/downloadclient", "implementation": "QBittorrent",
                            "name": "Stackarr qBittorrent", "fields": fields, "kind": "download client",
                            "extra": {"enable": True, "priority": 1, "removeCompletedDownloads": False,
                                      "removeFailedDownloads": False}})
    prowlarr = config.integrations["prowlarr"]
    if prowlarr.enabled and not prowlarr.read_only:
        for target in ("sonarr", "radarr"):
            integration = config.integrations[target]
            if not integration.enabled:
                continue
            check = {"source": "prowlarr", "target": target, "state": "unavailable"}
            checks.append(check)
            if not store.secret("prowlarr").get("api_key") or not store.secret(target).get("api_key"):
                continue
            changes.append({"source": "prowlarr", "target": "prowlarr", "check": check,
                            "base": address("prowlarr", prowlarr),
                            "key": store.secret("prowlarr")["api_key"], "path": "/api/v1/applications",
                            "implementation": CATALOG[target]["name"], "name": "Stackarr " + CATALOG[target]["name"],
                            "fields": {"baseUrl": peer_address(target, integration), "prowlarrUrl": peer_address("prowlarr", prowlarr),
                                       "apiKey": store.secret(target)["api_key"]},
                            "kind": "application", "extra": {"syncLevel": "addOnly"}})
    prepared = []
    async with httpx.AsyncClient(timeout=5, trust_env=False, follow_redirects=False, transport=transport) as client:
        for change in changes:
            headers = {"X-Api-Key": change["key"]}
            try:
                response = await client.get(change["base"] + change["path"] + "/schema", headers=headers)
                response.raise_for_status()
                schemas = response.json()
                schema = next((s for s in schemas if s.get("implementation", "").lower() == change["implementation"].lower()), None)
                if schema is None:
                    raise WiringError("The application does not advertise a compatible connection schema.")
                payload = {k: schema[k] for k in ("implementation", "configContract", "implementationName", "fields") if k in schema}
                payload.update(name=change["name"], **change["extra"])
                available = {f["name"] for f in payload.get("fields", [])}
                if change["kind"] == "download client":
                    category = "tvCategory" if change["target"] == "sonarr" else "movieCategory"
                    category = category if category in available else "category"
                    required = {"host", "port", "username", "password", category}
                    change["fields"][category] = change["fields"]["category"]
                else:
                    required = {"baseUrl", "apiKey"}
                if not required.issubset(available):
                    raise WiringError("The advertised schema is missing required fields; configure this connection manually.")
                for field in payload["fields"]:
                    if field["name"] in change["fields"]:
                        field["value"] = change["fields"][field["name"]]
                # Read existing entries now and again during apply; never overwrite them.
                existing = await client.get(change["base"] + change["path"], headers=headers)
                existing.raise_for_status()
                rows = existing.json()
                if any(r.get("implementation", "").lower() == change["implementation"].lower() for r in rows):
                    change["check"]["state"] = "preserved"
                    notices.append(f"{change['target']}: an existing {change['implementation']} connection is preserved; no change proposed.")
                    continue
                change["check"]["state"] = "proposed"
                prepared.append({**change, "payload": payload})
            except (httpx.HTTPError, ValueError, TypeError, KeyError, WiringError):
                notices.append(f"{change['target']}: unable to prepare a compatible {change['kind']}; check credentials and configure manually if needed.")
        from .seerr_wiring import build

        seerr_changes, seerr_notices = await build(store, client, checks=checks)
        prepared.extend(seerr_changes)
        notices.extend(seerr_notices)
        from .plex_wiring import build as build_plex

        plex_changes, plex_notices = await build_plex(store, client, checks=checks)
        prepared.extend(plex_changes)
        notices.extend(plex_notices)
        from .import_refresh import ImportRefresh

        discovery_changes, discovery_notices = await ImportRefresh(store, transport).review(client)
        prepared.extend(discovery_changes)
        checks.extend(change['check'] for change in discovery_changes)
        notices.extend(discovery_notices)
    writable = []
    for change in prepared:
        involved = {change.get("source"), change.get("target"), change.get("check", {}).get("source"), change.get("check", {}).get("target")} - {None}
        if any(config.integrations[key].read_only for key in involved):
            notices.append("Imported native app connections are read-only; existing settings are preserved.")
            if change.get("check"):
                change["check"]["state"] = "read-only"
        else:
            writable.append(change)
    return {"revision": revision, "changes": writable, "notices": list(dict.fromkeys(notices)), "checks": checks}


async def apply_plan(store, plan, transport=None):
    if store.config()[0] != plan["revision"]:
        raise WiringError("Settings changed; generate a fresh connection preview.")
    for change in plan["changes"]:
        involved = {change.get("source"), change.get("target"), change.get("check", {}).get("source"), change.get("check", {}).get("target")} - {None}
        try:
            require_writable(store, *involved)
        except ValueError as exc:
            raise WiringError(str(exc)) from None
    results = []
    async with httpx.AsyncClient(timeout=8, trust_env=False, follow_redirects=False, transport=transport) as client:
        for change in plan["changes"]:
            if change['kind'] == 'Plex import discovery':
                from .import_refresh import ImportRefresh

                try:
                    results.append(await ImportRefresh(store, transport).apply(client, change))
                except (httpx.HTTPError, ValueError, TypeError, KeyError, Conflict, IntegrationError):
                    store.audit('connection.failed', change['target'])
                    results.append({'target': change['target'], 'state': 'failed; review import discovery again'})
                continue
            if change["kind"] in {"Plex import refresh", "Plex availability schedule"}:
                from .plex_wiring import apply as apply_plex

                try:
                    results.append(await apply_plex(store, client, change))
                except (httpx.HTTPError, ValueError, TypeError, KeyError, StopIteration, Conflict):
                    store.audit("connection.failed", change["target"])
                    results.append({"target": change["target"], "state": "failed; inspect application and re-preview before retrying"})
                continue
            if change["target"] == "seerr":
                from .seerr_wiring import apply

                try:
                    results.append(await apply(store, client, change))
                except (httpx.HTTPError, ValueError, TypeError, KeyError, Conflict):
                    store.audit("connection.failed", "seerr")
                    results.append({"target": "seerr", "state": "failed; inspect application and re-preview before retrying"})
                continue
            require_write(change["target"], "download-client.create" if change["kind"] == "download client" else "application.create")
            headers = {"X-Api-Key": change["key"]}
            endpoint = change["base"] + change["path"]
            try:
                response = await client.get(endpoint, headers=headers)
                response.raise_for_status()
                if any(r.get("implementation", "").lower() == change["implementation"].lower() for r in response.json()):
                    results.append({"target": change["target"], "state": "preserved existing"})
                    continue
                # Supported Arr APIs expose a connection test endpoint before creation.
                response = await client.post(endpoint + "/test", headers=headers, json=change["payload"])
                response.raise_for_status()
                response = await client.post(endpoint, headers=headers, json=change["payload"])
                response.raise_for_status()
                store.audit("connection.created", change["target"])
                results.append({"target": change["target"], "state": "created"})
            except (httpx.HTTPError, ValueError, TypeError):
                store.audit("connection.failed", change["target"])
                results.append({"target": change["target"], "state": "failed; inspect application and re-preview before retrying"})
    return results
