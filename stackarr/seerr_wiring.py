"""Reviewed creation of initially missing Seerr Arr connections (verified Seerr v3 API)."""

from urllib.parse import urlsplit

import httpx

from .adapters import require_write
from .config import CATALOG
from .quality import select_profile
from .store import Conflict


async def build(store, client, *, checks=None):
    revision, config = store.config()
    app, credential = config.integrations["seerr"], store.secret("seerr")
    changes, notices = [], []
    selected = {target: {"source": target, "target": "seerr", "state": "unavailable"}
                for target in ("sonarr", "radarr") if app.enabled and config.integrations[target].enabled}
    if checks is not None:
        checks.extend(selected.values())
    if not app.enabled or not credential.get("api_key"):
        return changes, notices
    base, key = app.url, credential["api_key"]
    headers = {"X-Api-Key": key}
    try:
        response = await client.get(base + "/api/v1/status", headers=headers, params={"checkUpdateAvailable": "false"})
        response.raise_for_status()
        if not str(response.json().get("version", "")).startswith("3."):
            raise ValueError("Unsupported Seerr version")
        for target in ("sonarr", "radarr"):
            arr, secret = config.integrations[target], store.secret(target)
            if not arr.enabled or not secret.get("api_key"):
                continue
            path = "/api/v1/settings/" + target
            response = await client.get(base + path, headers=headers)
            response.raise_for_status()
            if response.json():
                selected[target]["state"] = "preserved"
                notices.append(f"Seerr: your existing {CATALOG[target]['name']} settings are preserved.")
                continue
            arr_headers = {"X-Api-Key": secret["api_key"]}
            response = await client.get(arr.url + "/api/v3/qualityprofile", headers=arr_headers)
            response.raise_for_status()
            profiles = response.json()
            response = await client.get(arr.url + "/api/v3/rootfolder", headers=arr_headers)
            response.raise_for_status()
            roots = response.json()
            expected_root = "/data/media/" + ("tv" if target == "sonarr" else "movies")
            root = next((row for row in roots if row.get("path") == expected_root), None)
            if not profiles or root is None:
                raise ValueError("Choose an existing Arr profile and library folder first")
            if arr.quality_profile:
                try:
                    profile = select_profile(profiles, arr.quality_profile)
                except ValueError:
                    notices.append(f"Seerr: the selected {arr.quality_profile} profile is unavailable in {CATALOG[target]['name']}. Restore it before reviewing this connection again.")
                    continue
            else:
                profile = profiles[0]
                if type(profile.get("id")) is not int:
                    raise ValueError("Choose a valid Arr profile first")
            peer = urlsplit(arr.peer_url or arr.url)
            payload = {"name": "Stackarr " + CATALOG[target]["name"], "hostname": peer.hostname,
                       "port": peer.port or (443 if peer.scheme == "https" else 80), "useSsl": peer.scheme == "https",
                       "baseUrl": peer.path.rstrip("/"), "apiKey": secret["api_key"],
                       "activeProfileId": profile["id"], "activeProfileName": profile["name"],
                       "activeDirectory": root["path"], "is4k": False, "isDefault": True, "tags": [],
                       "syncEnabled": True, "preventSearch": False, "tagRequests": False, "overrideRule": []}
            if target == "radarr":
                payload["minimumAvailability"] = "released"
            else:
                payload.update(seriesType="standard", animeSeriesType="anime", enableSeasonFolders=True, monitorNewItems="none")
            selected[target]["state"] = "proposed"
            changes.append({"source": target, "target": "seerr", "check": selected[target],
                            "base": base, "key": key, "path": path,
                            "implementation": CATALOG[target]["name"], "name": payload["name"],
                            "kind": "request service", "payload": payload, "revision": revision,
                            "detail": f"Use profile {profile['name']} and library {root['path']} for standard requests. Existing profiles stay unchanged."})
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return [], ["Seerr: could not prepare compatible Arr settings. Finish Seerr's Plex setup and check the saved connections."]
    return changes, notices


async def apply(store, client, change):
    require_write("seerr", "arr-connection.create")
    if store.config()[0] != change["revision"] or store.secret("seerr").get("api_key") != change["key"]:
        raise Conflict("Settings changed. Preview Seerr connections again.")
    headers = {"X-Api-Key": change["key"]}
    url, payload = change["base"] + change["path"], change["payload"]
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    if response.json():
        return {"target": "seerr", "state": "preserved existing"}
    response = await client.post(url + "/test", headers=headers, json=payload)
    response.raise_for_status()
    tested = response.json()
    if (not any(row.get("id") == payload["activeProfileId"] and row.get("name") == payload["activeProfileName"] for row in tested["profiles"])
            or not any(row.get("path") == payload["activeDirectory"] for row in tested["rootFolders"])):
        raise ValueError("The tested profile or library changed")
    if store.config()[0] != change["revision"]:
        raise Conflict("Settings changed during connection test. Preview again.")
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    if response.json():
        return {"target": "seerr", "state": "preserved existing"}
    response = await client.post(url, headers=headers, json=payload)
    response.raise_for_status()
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    if not any(all(row.get(name) == value for name, value in payload.items()) for row in response.json()):
        raise ValueError("Seerr connection readback changed")
    store.audit("connection.created", "seerr")
    return {"target": "seerr", "state": "created"}
